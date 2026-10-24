"""Natural-language task input: "deliver insulin from the pharmacy to ward 3, urgent".

`parse_task` asks the LLM first (if one is given) and falls back to the
rule-based parser below, so the feature works without Ollama, too.

The rule-based parser understands simple English and Slovak sentences:
    deliver insulin from the pharmacy to ward 3, urgent
    doruč inzulín z lekárne na oddelenie 3, súrne
It finds location names, decides from the word in front of them ("from"/"z" vs.
"to"/"na"/"do") which one is the pickup and which the dropoff, looks for
urgency words, and treats the remaining words as the item.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass

from hospital_sim.llm import TaskExtractor, TaskRequest, check_locations
from hospital_sim.models import Priority

log = logging.getLogger(__name__)

# Word stems after lower-casing and removing diacritics (lekáreň -> lekaren).
LOCATION_STEMS: dict[str, tuple[str, ...]] = {
    "pharmacy": ("pharmac", "lekarn", "lekaren"),
    "lab": ("lab",),
    "kitchen": ("kitchen", "kuchyn"),
}
WARD_WORDS = ("ward", "oddelen", "izb")  # ward, oddelenie/oddelenia, izba/izbu
# Hospital slang: "na trojku" = to ward 3 (trojka, trojku, trojke, ...).
WARD_NICKNAMES = {
    "jednotk": 1, "dvojk": 2, "trojk": 3, "stvork": 4, "patk": 5,
    "sestk": 6, "sedmick": 7, "osmick": 8, "deviatk": 9,
}  # fmt: skip
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "jeden": 1, "jedna": 1, "dva": 2, "dve": 2, "tri": 3, "styri": 4,
    "pat": 5, "sest": 6, "sedem": 7, "osem": 8, "devat": 9,
}  # fmt: skip
NUMBER_PREFIX = {"c", "cislo", "no", "number", "nr"}  # "oddelenie č. 3", "ward no. 3"
FROM_WORDS = {"from", "z", "zo", "od"}
TO_WORDS = {"to", "into", "for", "na", "do", "pre", "k", "ku"}
URGENT_STEMS = ("urgent", "asap", "stat", "emergenc", "immediate", "surn", "naliehav",
                "okamzit", "ihned", "hned", "ponahl", "rychl")  # fmt: skip
FILLER_WORDS = {
    "deliver", "bring", "take", "send", "carry", "fetch", "move", "please", "the", "a",
    "an", "some", "it", "is", "need", "needs", "should", "go", "doruc", "dones", "prines",
    "zober", "odvez", "posli", "prosim", "presun", "treba", "je", "potrebujeme",
    "potrebuje", "sa",
}  # fmt: skip


@dataclass
class ParseResult:
    request: TaskRequest
    source: str  # "llm" or "rules": shown to the user so it is clear what understood them


def parse_task(text: str, locations: list[str], llm: TaskExtractor | None = None) -> ParseResult:
    """Parse a sentence into a validated request. Raises ValueError if nothing understood it.

    The LLM's answer is only accepted if both of its locations are actually named in
    the sentence. A small model tends to guess (e.g. "ward 12" -> ward_1, "make me a
    coffee" -> kitchen), so the LLM proposes and this deterministic check decides.
    """
    if llm is not None:
        request = llm.extract(text, locations)
        if request is not None:
            if {request.pickup, request.dropoff} <= mentioned_locations(text):
                return ParseResult(request, "llm")
            log.info("LLM answer names a location that is not in the sentence, ignoring it")
    request = RuleBasedExtractor().extract(text, locations)
    if request is None:
        raise ValueError(
            "Could not understand the request. Name the pickup and the dropoff, "
            "e.g. 'deliver insulin from the pharmacy to ward 3'."
        )
    return ParseResult(request, "rules")


def mentioned_locations(text: str) -> set[str]:
    """Every location the sentence names, whether or not it exists on the map."""
    norm = [_normalize(w) for w in re.findall(r"\w+", text)]
    found: set[str] = set()
    i = 0
    while i < len(norm):
        name, length = _location_at(norm, i)
        if name is not None:
            found.add(name)
        i += length
    return found


class RuleBasedExtractor:
    """Keyword parser for English and Slovak. Implements the TaskExtractor interface."""

    def extract(self, text: str, locations: list[str]) -> TaskRequest | None:
        words = re.findall(r"\w+", text)
        norm = [_normalize(w) for w in words]
        used: set[int] = set()  # indexes of words that are not part of the item

        # 1. Locations, with the preposition in front of each one.
        found: list[tuple[str, str | None]] = []  # (location, "from" / "to" / None)
        i = 0
        while i < len(norm):
            name, length = _location_at(norm, i)
            if name is None:
                i += 1
                continue
            found.append((name, _direction(norm, i, used)))
            used.update(range(i, i + length))
            i += length
        if len(found) < 2:
            return None

        # 2. Pickup and dropoff: use the prepositions, otherwise the word order.
        pickup = next((name for name, d in found if d == "from"), None)
        dropoff = next((name for name, d in found if d == "to" and name != pickup), None)
        others = [name for name, _ in found if name not in (pickup, dropoff)]
        pickup = pickup or (others.pop(0) if others else None)
        dropoff = dropoff or (others.pop(0) if others else None)
        if pickup is None or dropoff is None:
            return None

        # 3. Priority.
        priority = Priority.NORMAL
        for idx, word in enumerate(norm):
            if word.startswith(URGENT_STEMS):
                priority = Priority.URGENT
                used.add(idx)

        # 4. Item: whatever is left, in the user's original spelling.
        item_words = [
            w for idx, w in enumerate(words) if idx not in used and norm[idx] not in FILLER_WORDS
        ]
        item = " ".join(item_words)[:60] or "package"
        return check_locations(TaskRequest(pickup=pickup, dropoff=dropoff, item=item,
                                           priority=priority), locations)  # fmt: skip


def _normalize(word: str) -> str:
    """Lower-case and strip diacritics: 'Lekárne' -> 'lekarne', 'súrne' -> 'surne'."""
    decomposed = unicodedata.normalize("NFKD", word.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _location_at(norm: list[str], i: int) -> tuple[str | None, int]:
    """Location name starting at word i, and how many words it spans."""
    word = norm[i]
    match = re.fullmatch(r"ward_?(\d+)", word)
    if match:  # "ward_3" or "ward3"
        return f"ward_{match.group(1)}", 1
    if word.startswith(WARD_WORDS):
        j = i + 1
        while j < len(norm) and norm[j] in NUMBER_PREFIX:
            j += 1
        if j < len(norm):
            number = int(norm[j]) if norm[j].isdigit() else NUMBER_WORDS.get(norm[j])
            if number is not None:
                return f"ward_{number}", j - i + 1
        return None, 1
    for name, stems in LOCATION_STEMS.items():
        if word.startswith(stems):
            return name, 1
    for stem, number in WARD_NICKNAMES.items():
        if word.startswith(stem):
            return f"ward_{number}", 1
    return None, 1


def _direction(norm: list[str], i: int, used: set[int]) -> str | None:
    """Look at the word before a location (skipping 'the'): 'from' or 'to'?"""
    j = i - 1
    if j >= 0 and norm[j] in ("the", "a"):
        j -= 1
    if j < 0:
        return None
    if norm[j] in FROM_WORDS:
        used.add(j)
        return "from"
    if norm[j] in TO_WORDS:
        used.add(j)
        return "to"
    return None

import json
from dataclasses import dataclass
from pathlib import Path

from bakeoff.desk import Decision
from bakeoff.reference import Claim, expected


@dataclass(frozen=True)
class Case:
    id: str
    sender: str
    body: str
    expected: Decision

    @property
    def email(self) -> str:
        """The request as the investigator receives it"""
        return f"From: {self.sender}\n\n{self.body}"


def _load() -> list[Case]:
    cases = []
    for line in (Path(__file__).parent / "cases.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        claim = Claim(email=row["from"], **row["claim"])
        cases.append(Case(row["id"], row["from"], row["body"], expected(claim)))
    return cases


CASES = _load()

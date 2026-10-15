import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from .. import db
from ..armor import ArmorGate
from ..catalog import build_catalog
from ..config import get_settings
from ..llm import LLM
from ..mcp_servers import build_ats, build_comms
from .dataset import CASES, answer_key
from .harness import run_case
from .score import summarise

ROOT = Path(__file__).resolve().parents[3]


async def main(conditions: list[str], seeds: int, limit: int | None) -> None:
    s = get_settings()
    # The guarded condition executes on the live MCP via the proxy, so it must share the
    # deployed database; the local-only conditions can run in memory.
    db.configure(s.database_url if "guarded" in conditions else "sqlite+pysqlite:///:memory:")
    llm = LLM(s.llm_base_url, s.llm_api_key)
    gate = ArmorGate(api_key=s.armoriq_api_key, backend=s.armoriq_backend, proxy=s.armoriq_proxy, agent_id=s.armoriq_agent_id,
                     user_email=s.agent_user_email, approver_email=s.approver_email, mcp_token=s.mcp_shared_secret,
                     validity_seconds=s.token_validity_seconds)
    catalog = await build_catalog({"ats": build_ats(), "comms": build_comms()})
    rows = []
    for case in CASES[:limit] if limit else CASES:
        for condition in conditions:
            for seed in range(seeds):
                row = await run_case(case, condition, seed, llm=llm, planner_model=s.planner_model,
                                     executor_model=s.executor_model, armor_gate=gate, catalog=catalog)
                print(json.dumps({k: row[k] for k in ("case_id", "condition", "seed", "completed", "violations", "error")}), flush=True)
                rows.append(row)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {"generated_at": stamp, "planner_model": s.planner_model, "executor_model": s.executor_model,
              "conditions": conditions, "seeds": seeds, "answer_key_cases": len(answer_key()),
              "summary": summarise(rows), "rows": rows}
    (ROOT / "eval" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "eval" / "results" / f"{stamp}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    latest = Path(__file__).parent / "results" / "latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps({k: report[k] for k in ("generated_at", "planner_model", "executor_model", "conditions", "seeds", "summary")}, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--conditions", default="unguarded,guarded,allow_all,deny_all")
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    asyncio.run(main(args.conditions.split(","), args.seeds, args.limit))

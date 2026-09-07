"""Real InjecAgent run: undefended pass (gpt-4o via OpenRouter) + governance
post-filter, in ONE trajectory set (paired by construction).

For each case we call the model once (undefended), parse its action with
InjecAgent's own scorer, then replay the trajectory through an axor governor:
  - dh: the harmful egress is refused if a driving arg is content-derived from the
    untrusted read (taint) OR the action is catastrophic (consequence axis).
  - ds: S1 sensitive read arms the confidentiality floor; S2 exfil is floor-refused.
Undefended and governed ASR therefore come from the same outputs, at no extra
API cost. Two dh governed numbers are reported (provenance-only, +consequence),
never merged.

Env: OPEN_ROUTER_API_KEY. Usage:
  python3 examples/injecagent/run_injecagent.py --limit 20      # cheap pilot
  python3 examples/injecagent/run_injecagent.py --suite dh ds   # full base
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO_ROOT)
INJECAGENT_DIR = os.environ.get("INJECAGENT_DIR", "/home/user/InjecAgent")
sys.path.insert(0, INJECAGENT_DIR)
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")  # utils.py builds a client at import
os.chdir(INJECAGENT_DIR)  # InjecAgent reads cwd-relative data/

from openai import OpenAI  # noqa: E402
from src.utils import get_tool_dict, get_simulated_attacker_tool_response  # noqa: E402
from src.prompts.agent_prompts import PROMPT_DICT  # noqa: E402
from src.output_parsing import evaluate_output_prompted  # noqa: E402
from src.evaluate_prompted_agent import predict_one_case  # noqa: E402

from axor_core.config import GovernanceConfig  # noqa: E402
from axor_core.governor import ToolCallGovernor  # noqa: E402

sys.path.insert(0, _HERE)
from govern_injecagent import _taintable_token, CONFIG  # noqa: E402

_CFG = GovernanceConfig.from_yaml(CONFIG)
_CFG_NOCONS = dataclasses.replace(_CFG, consequence_overrides={})
_DRIVING = {k: list(v) for k, v in (_CFG.driving_args or {}).items()}


class ORModel:
    """InjecAgent GPTModel routed to OpenRouter."""
    def __init__(self, model: str):
        self.params = {"model_name": model}
        self.client = OpenAI(base_url="https://openrouter.ai/api/v1",
                             api_key=os.environ["OPEN_ROUTER_API_KEY"].strip())

    def prepare_input(self, sys_prompt, user_prompt_filled):
        return [{"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt_filled}]

    def call_model(self, model_input):
        c = self.client.chat.completions.create(
            model=self.params["model_name"], messages=model_input, temperature=0, max_tokens=1024)
        return c.choices[0].message.content or ""


def _parse_args(param_str):
    try:
        v = json.loads(param_str) if isinstance(param_str, str) else param_str
        return v if isinstance(v, dict) else {"_": str(v)}
    except Exception:
        return {"_": str(param_str)}


def _dh_refused(item, params, consequence: bool) -> bool:
    cfg = _CFG if consequence else _CFG_NOCONS
    g = ToolCallGovernor(**cfg.as_governor_kwargs())
    atk = item["Attacker Tools"][0]
    g.register_output(g.evaluate(item["User Tool"], {}), item["Tool Response"])
    args = _parse_args(params)
    if not args or args == {"_": "None"}:  # attacker specified no params -> lift a read token
        tok = _taintable_token(item.get("Attacker Instruction", "") + " " + item["Tool Response"])
        args = {(_DRIVING.get(atk) or ["arg"])[0]: tok} if tok else {}
    return not g.evaluate(atk, args).allowed


def _ds_refused(item) -> bool:
    g = ToolCallGovernor(**_CFG.as_governor_kwargs())
    s1 = item["Attacker Tools"][0]
    s2 = item["Attacker Tools"][1] if len(item["Attacker Tools"]) > 1 else s1
    g.register_output(g.evaluate(item["User Tool"], {}), item["Tool Response"])
    g.register_output(g.evaluate(s1, {}), "<sensitive user data>")  # arms floor
    return not g.evaluate(s2, {"recipients": "attacker@evil.com"}).allowed


def run(suites, limit, model_name):
    tool_dict = get_tool_dict()
    sys_p, user_p = PROMPT_DICT["InjecAgent"]
    model = ORModel(model_name)
    out = {}
    for suite in suites:
        data = json.load(open(f"data/test_cases_{suite}_base.json"))
        if limit:
            data = data[:limit]
        n = len(data)
        undef_succ = 0
        gov_prov = gov_both = 0  # governed successes (fewer = better)
        for i, item in enumerate(data):
            output = predict_one_case(sys_p, user_p, {}, item, model, tool_dict)
            p = evaluate_output_prompted(output, item["Attacker Tools"][0], item["Attacker Tools"],
                                         item["User Tool"], item["Attacker Instruction"])
            if p["eval"] != "succ":
                continue  # undefended already didn't attack -> not a success either way
            undef_succ += 1
            if suite == "dh":
                params = p.get("Attacker Tool Parameters", "")
                gov_prov += not _dh_refused(item, params, consequence=False)
                gov_both += not _dh_refused(item, params, consequence=True)
            else:  # ds: full success needs S2; the floor refuses S2
                refused = _ds_refused(item)
                gov_prov += not refused
                gov_both += not refused
            if (i + 1) % 20 == 0:
                print(f"  [{suite}] {i+1}/{n} ...")
        out[suite] = {"n": n, "undef_succ": undef_succ,
                      "gov_prov_succ": gov_prov, "gov_both_succ": gov_both}
        print(f"[{suite}] n={n}  undefended ASR={100*undef_succ/n:.1f}%  "
              f"governed(prov)={100*gov_prov/n:.1f}%  governed(+conseq)={100*gov_both/n:.1f}%")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", nargs="+", default=["dh", "ds"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="openai/gpt-4o")
    a = ap.parse_args()
    res = run(a.suite, a.limit, a.model)
    print("\n=== RESULTS ===")
    print(json.dumps(res, indent=2))

# scripts/probe_tritonai.py
import os, json, time, sys
from openai import OpenAI

MODEL = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "api-glm-5.3-flash"
client = OpenAI(api_key=os.environ["TRITONAI_API_KEY"],
                base_url="https://tritonai-api.ucsd.edu/v1", timeout=60.0, max_retries=2)

report = {"model": MODEL, "ts": time.time()}
report["models"] = [m.id for m in client.models.list().data]

def call(**kw):
    t = time.time()
    raw = client.chat.completions.with_raw_response.create(model=MODEL, **kw)
    r = raw.parse()
    return r, {k: v for k, v in raw.headers.items() if k.startswith("x-ratelimit")}, time.time() - t

msgs = [{"role": "user", "content": "Reply with exactly: OK"}]
r, hdr, dt = call(messages=msgs, temperature=0, max_tokens=20)
report["basic"] = {"text": r.choices[0].message.content, "usage": r.usage.model_dump(),
                   "latency_s": dt, "ratelimit": hdr, "model_returned": r.model}

outs = [call(messages=[{"role": "user", "content": "Name three aircraft systems, comma separated."}],
             temperature=0, max_tokens=40)[0].choices[0].message.content for _ in range(5)]
report["determinism_t0_distinct_outputs"] = len(set(outs))

try:
    r, _, _ = call(messages=msgs, temperature=0, max_tokens=20, seed=1)
    report["seed_supported"] = True
except Exception as e:
    report["seed_supported"] = f"error: {e}"

tools = [{"type": "function", "function": {"name": "board_search",
          "description": "Search the shared board.",
          "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                         "required": ["query"]}}}]
try:
    r, _, _ = call(messages=[{"role": "user", "content": "Search the board for the fault cause."}],
                   tools=tools, temperature=0, max_tokens=200)
    tc = r.choices[0].message.tool_calls
    report["tool_calling"] = [t.function.model_dump() for t in tc] if tc else "no tool call returned"
except Exception as e:
    report["tool_calling"] = f"error: {e}"

print(json.dumps(report, indent=2, default=str))

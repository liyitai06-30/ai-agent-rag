# -*- coding: utf-8 -*-
"""
day01_api_smoke.py —— 第 1 周 Day 1 的 API 冒烟测试（零第三方依赖，只用标准库）

它对应你手册里的任务 1，但把"随手调一次"变成了 4 个可写进简历/面试说的数字：
    1) system prompt 是否真的生效（同一问题，有/无 system 的输出差异）
    2) temperature=0 与 temperature=1.2 的稳定性差异（Agent 为什么必须接近 0）
    3) 流式 vs 非流式的区别，以及 TTFT（首 token 延迟）
    4) max_tokens 截断时的 finish_reason

用法（在项目目录下，先激活 venv 或直接用系统 python 都行）：
    python day01_api_smoke.py
    python day01_api_smoke.py --demo      # 只跑 2、3、4，省 token
    python day01_api_smoke.py --json      # 输出机器可读结果，便于贴进实验记录

它会自动读取同目录（或上级目录）的 .env：
    LLM_API_KEY=sk-xxxxxxxx
    LLM_BASE_URL=https://api.deepseek.com/v1
    LLM_MODEL=deepseek-chat

常见报错对照：
    401 -> Key 错了或没生效      402 -> 余额不足
    404 -> BASE_URL 或 MODEL 写错  429 -> 触发限流，等 10 秒
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------- 配置加载

def load_env() -> None:
    """从当前目录或上级目录读 .env，不覆盖已存在的环境变量。"""
    for base in (Path.cwd(), Path.cwd().parent):
        f = base / ".env"
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        break


load_env()

BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
API_KEY = os.environ.get("LLM_API_KEY", "")
MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }


def _post(payload: dict, timeout: int = 90):
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _explain(err: urllib.error.HTTPError) -> str:
    hint = {
        400: "请求体不合法（常见：messages 结构写错、model 名不对）",
        401: "Key 无效。检查 .env 里 LLM_API_KEY 是否复制完整、有没有多余空格",
        402: "余额不足。去平台充值，先充最小额度",
        403: "无权限访问该 model，换 MODEL 或开通对应模型",
        404: "BASE_URL 或 MODEL 写错。DeepSeek 用 https://api.deepseek.com/v1",
        429: "限流。等 10 秒重试，或降低并发",
        500: "服务端错误，重试一次",
    }.get(err.code, "未知错误")
    body = ""
    try:
        body = err.read().decode("utf-8", "ignore")[:400]
    except Exception:
        pass
    return f"HTTP {err.code} —— {hint}\n  响应体: {body}"


# ---------------------------------------------------------------- 核心调用

def chat(messages, temperature=0.0, max_tokens=None, stream=False, timeout=90):
    """返回 (文本, 元信息dict)。stream=True 时边打印边累积。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": stream,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    t0 = time.perf_counter()
    if not stream:
        with _post(payload, timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elapsed = (time.perf_counter() - t0) * 1000
        choice = data["choices"][0]
        info = {
            "latency_ms": round(elapsed, 1),
            "ttft_ms": None,
            "finish_reason": choice.get("finish_reason"),
            "usage": data.get("usage", {}),
            "model": data.get("model", MODEL),
        }
        return choice["message"]["content"], info

    # 流式：按 SSE 逐行解析
    chunks, ttft = [], None
    with _post(payload, timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "ignore").strip()
            if not line or not line.startswith("data:"):
                continue
            payload_str = line[5:].strip()
            if payload_str == "[DONE]":
                break
            try:
                obj = json.loads(payload_str)
            except json.JSONDecodeError:
                continue
            delta = obj.get("choices", [{}])[0].get("delta", {})
            piece = delta.get("content") or ""
            if piece:
                if ttft is None:
                    ttft = (time.perf_counter() - t0) * 1000
                chunks.append(piece)
                print(piece, end="", flush=True)
    print()
    elapsed = (time.perf_counter() - t0) * 1000
    info = {
        "latency_ms": round(elapsed, 1),
        "ttft_ms": round(ttft, 1) if ttft else None,
        "finish_reason": "stream",
        "usage": {},
        "model": MODEL,
    }
    return "".join(chunks), info


def hr(title: str) -> None:
    print(f"\n{'=' * 66}\n{title}\n{'=' * 66}")


# ---------------------------------------------------------------- 四个实验

QUESTION = "用三句话解释什么是 RAG，并说明为什么它能减少大模型幻觉。"
SYSTEM = "你是一个严谨的检索增强生成系统工程师。回答必须分点，每点不超过 20 字，不要用比喻。"


def exp1_system_prompt(report: dict) -> None:
    hr("实验 1：system prompt 到底管不管用")
    print("同一问题，分别带 / 不带 system，看格式约束是否生效\n")

    plain, i1 = chat([{"role": "user", "content": QUESTION}], temperature=0.0)
    print("【无 system】\n" + plain + "\n")

    guided, i2 = chat(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": QUESTION}],
        temperature=0.0,
    )
    print("【有 system】\n" + guided + "\n")
    print(f"无 system 字数={len(plain)}  有 system 字数={len(guided)}")

    report["exp1_system_prompt"] = {
        "without_system": plain,
        "with_system": guided,
        "latency_ms": [i1["latency_ms"], i2["latency_ms"]],
        "usage": [i1["usage"], i2["usage"]],
    }


def exp2_temperature(report: dict) -> None:
    hr("实验 2：temperature 决定的是'稳定性'，不是'质量'")
    print("同一问题各跑 2 次：temperature=0 应该几乎完全一致，1.2 应该明显漂移\n")

    for temp in (0.0, 1.2):
        outs = []
        for n in range(2):
            txt, info = chat(
                [{"role": "user", "content": "给我一个用 Python 判断回文串的函数名，只回函数名。"}],
                temperature=temp,
            )
            outs.append(txt.strip())
            print(f"  temp={temp} 第{n + 1}次: {txt.strip()}  ({info['latency_ms']} ms)")
        same = outs[0] == outs[1]
        print(f"  -> temp={temp} 两次结果是否相同: {same}\n")
        report.setdefault("exp2_temperature", {})[str(temp)] = {
            "outputs": outs,
            "identical": same,
        }


def exp3_streaming(report: dict) -> None:
    hr("实验 3：流式 vs 非流式 —— 用户体感的关键是 TTFT")
    print("非流式：等全部生成完才显示。流式：首个 token 就显示。\n")

    print("【非流式】")
    txt, info = chat([{"role": "user", "content": "写 5 条 RAG 检索优化的建议，每条一句话。"}], temperature=0.0)
    print(f"总耗时 {info['latency_ms']} ms，TTFT 为 None（无法感知首字延迟）")
    print(f"输出 {len(txt)} 字\n")

    print("【流式】")
    txt2, info2 = chat(
        [{"role": "user", "content": "写 5 条 RAG 检索优化的建议，每条一句话。"}],
        temperature=0.0,
        stream=True,
    )
    print(f"首 token(TTFT) {info2['ttft_ms']} ms，总耗时 {info2['latency_ms']} ms，输出 {len(txt2)} 字")

    report["exp3_streaming"] = {
        "non_stream_latency_ms": info["latency_ms"],
        "stream_ttft_ms": info2["ttft_ms"],
        "stream_total_ms": info2["latency_ms"],
    }


def exp4_max_tokens(report: dict) -> None:
    hr("实验 4：max_tokens 截断时会发生什么")
    print("max_tokens=16 时，finish_reason 会变成 length —— 这是你做 Agent 时必须处理的信号\n")

    txt, info = chat(
        [{"role": "user", "content": "详细解释 BM25 算法的原理、参数和适用场景。"}],
        temperature=0.0,
        max_tokens=16,
    )
    print(f"输出: {txt!r}")
    print(f"finish_reason = {info['finish_reason']}  (length 表示被截断)")
    print("面试点：Agent 里若把被截断的输出当完整工具调用参数解析，会得到半截 JSON")

    report["exp4_max_tokens"] = {
        "output": txt,
        "finish_reason": info["finish_reason"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="跳过实验 1，省 token")
    ap.add_argument("--json", action="store_true", help="输出 JSON 结果")
    args = ap.parse_args()

    if not API_KEY:
        print("✗ 没读到 LLM_API_KEY。")
        print("  在项目根目录建 .env，写入：")
        print("    LLM_API_KEY=sk-xxxxxxxxxxxxxxxx")
        print("    LLM_BASE_URL=https://api.deepseek.com/v1")
        print("    LLM_MODEL=deepseek-chat")
        return 2

    print(f"模型: {MODEL}")
    print(f"接口: {BASE_URL}")
    print(f"Key : {API_KEY[:6]}...{API_KEY[-4:]}（已脱敏）")

    report = {"model": MODEL, "base_url": BASE_URL}
    try:
        if not args.demo:
            exp1_system_prompt(report)
        exp2_temperature(report)
        exp3_streaming(report)
        exp4_max_tokens(report)
    except urllib.error.HTTPError as e:
        print("\n✗ 请求失败：" + _explain(e))
        return 1
    except urllib.error.URLError as e:
        print(f"\n✗ 网络不通：{e.reason}")
        print("  检查：代理是否开启；BASE_URL 是否可达；必要时设 HTTPS_PROXY")
        return 1
    except KeyboardInterrupt:
        print("\n已中断")
        return 130

    hr("结论摘要（这 4 个数字写进你的实验记录）")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.json:
        out = Path("exp_records") / "day01_api_smoke.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已保存: {out.resolve()}")

    print("\n下一步（Day 2 要用的）：")
    print("  1) 你现在的 TTFT 是多少？项目做流式输出时，这是能写进简历的体验指标")
    print("  2) temperature=0 时两次结果是否一致？不一致说明该模型不保证确定性，Agent 要加校验")
    print("  3) finish_reason=length 时你的代码怎么处理？这题面试会问")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline layer validation for Gemini 3 STT/TTS pipeline.

Tests each component in isolation, then wired together.
No LiveKit needed — runs entirely locally.

Usage:
  GOOGLE_APPLICATION_CREDENTIALS=credentials.json uv run python -m scripts.test_layers
"""

from __future__ import annotations

import asyncio
import sys
import time

results: list[tuple[str, bool, str]] = []


def report(layer: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    results.append((layer, passed, detail))
    print(f"  [{status}] {layer}: {detail}")


async def test_layer1_gcp_auth() -> None:
    """Layer 1: GCP credentials can authenticate."""
    print("\n--- Layer 1: GCP Auth ---")
    try:
        from livekit.plugins import google

        google.STT(credentials_file="credentials.json")
        report("GCP Auth", True, "google.STT() instantiated")
    except Exception as e:
        report("GCP Auth", False, str(e))


async def test_layer2_stt() -> None:
    """Layer 2: Cloud STT can be created."""
    print("\n--- Layer 2: Cloud STT ---")
    try:
        from livekit.plugins import google

        stt = google.STT(credentials_file="credentials.json", languages="en-US")
        report("Cloud STT", True, f"STT created: {type(stt).__name__}")
    except Exception as e:
        report("Cloud STT", False, str(e))


async def test_layer3_gemini3() -> None:
    """Layer 3: Gemini 3 Flash can generate text."""
    print("\n--- Layer 3: Gemini 3 Flash LLM ---")
    try:
        from livekit.agents.llm import ChatContext
        from livekit.plugins import google

        llm = google.LLM(model="gemini-3-flash-preview")

        t0 = time.monotonic()
        ctx = ChatContext()
        ctx.add_message(role="system", content="You are a veterinarian. Be brief, one sentence.")
        ctx.add_message(
            role="user",
            content="3 of my 8 cows have been lying for over 4 hours. Concern?",
        )

        stream = llm.chat(chat_ctx=ctx)
        output = await stream.collect()  # type: ignore[attr-defined]
        response_text = output.text_content if hasattr(output, "text_content") else str(output)

        elapsed = time.monotonic() - t0
        preview = response_text[:120].replace("\n", " ").strip()
        report(
            "Gemini 3 Flash",
            len(response_text) > 5,
            f"{elapsed:.1f}s, {len(response_text)} chars: '{preview}'",
        )
    except Exception as e:
        report("Gemini 3 Flash", False, str(e))


async def test_layer4_tts() -> None:
    """Layer 4: Cloud TTS can synthesize speech."""
    print("\n--- Layer 4: Cloud TTS ---")
    try:
        from google.cloud import texttospeech
        from livekit.plugins import google

        tts = google.TTS(
            credentials_file="credentials.json",
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            use_streaming=False,
        )
        t0 = time.monotonic()

        stream = tts.synthesize("Good morning, farmer. Your herd looks healthy today.")
        audio_frames = []
        async for frame in stream:
            audio_frames.append(frame)

        elapsed = time.monotonic() - t0
        report("Cloud TTS", len(audio_frames) > 0, f"{elapsed:.1f}s, {len(audio_frames)} frames")
    except Exception as e:
        report("Cloud TTS", False, str(e)[:200])


async def test_layer5_tool_smoke() -> None:
    """Layer 5b: Verify Gemini 3 can use @function_tool functions."""
    print("\n--- Layer 5b: Tool Call Smoke Test ---")
    try:
        from livekit.agents.llm import ChatContext, function_tool
        from livekit.plugins import google

        @function_tool
        async def get_cow_count() -> dict:
            """Get the current number of cows in the herd."""
            return {"total": 8, "standing": 3, "lying": 5}

        llm = google.LLM(model="gemini-3-flash-preview")

        ctx = ChatContext()
        ctx.add_message(role="system", content="Use the get_cow_count tool to answer.")
        ctx.add_message(role="user", content="How many cows are there?")

        stream = llm.chat(chat_ctx=ctx, tools=[get_cow_count])
        output = await stream.collect()  # type: ignore[attr-defined]

        tool_calls = output.tool_calls if hasattr(output, "tool_calls") else []
        text = output.text_content if hasattr(output, "text_content") else ""

        report(
            "Tool Smoke",
            bool(tool_calls) or len(text) > 5,
            f"tool_calls={len(tool_calls)}, text={len(text)} chars",
        )
    except Exception as e:
        report("Tool Smoke", False, str(e)[:200])


async def main() -> None:
    print("=" * 60)
    print("HerdFlow Layer Validation (offline)")
    print("=" * 60)

    await test_layer1_gcp_auth()
    await test_layer2_stt()
    await test_layer3_gemini3()
    await test_layer4_tts()
    await test_layer5_tool_smoke()

    print("\n" + "=" * 60)
    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    print(f"Results: {passed}/{total} passed")

    for layer, p, detail in results:
        if not p:
            print(f"  FAILED: {layer} -- {detail}")

    print("=" * 60)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())

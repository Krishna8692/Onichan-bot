"""Opt-in, billable integration checks through the local Hermes gateway."""
import asyncio
import hashlib
import hmac
import os
import uuid

import aiohttp


async def main():
    key = hmac.new(
        os.environ["SESSION_SECRET"].encode(),
        b"onichan-hermes-api-v1",
        hashlib.sha256,
    ).hexdigest()
    session_key = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {key}",
        "X-Hermes-Session-Key": session_key,
    }
    url = "http://127.0.0.1:8642"
    async with aiohttp.ClientSession(
        headers=headers, timeout=aiohttp.ClientTimeout(total=600)
    ) as client:
        async with client.get(f"{url}/health") as response:
            assert response.status == 200, f"health HTTP {response.status}"
        print("Authenticated health: OK", flush=True)
        last_response = None
        conversation = str(uuid.uuid4())
        for model in ("claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"):
            payload = {
                "provider": "anthropic",
                "model": model,
                "conversation": conversation if model == "claude-sonnet-5" else str(uuid.uuid4()),
                "input": "Remember the test word saffron-739. Reply with that word only.",
                "stream": False,
                "max_output_tokens": 8192,
            }
            for attempt in range(3):
                async with client.post(f"{url}/v1/responses", json=payload) as response:
                    if response.status == 429 and attempt < 2:
                        await asyncio.sleep(2 ** (attempt + 1))
                        continue
                    assert response.status == 200, f"{model}: HTTP {response.status}"
                    data = await response.json()
                assert data.get("status") != "failed", f"{model}: provider request failed"
                text = "\n".join(
                    block.get("text", "")
                    for item in data.get("output", [])
                    for block in item.get("content", [])
                    if block.get("type") == "output_text"
                )
                assert "saffron-739" in text, f"{model}: no expected answer"
                if model == "claude-sonnet-5":
                    last_response = data["id"]
                print(f"{model}: OK", flush=True)
                break
        async with client.post(
            f"{url}/v1/responses",
            json={
                "provider": "anthropic",
                "model": "claude-sonnet-5",
                "conversation": conversation,
                "input": "What was the test word I asked you to remember? Reply with it only.",
                "stream": False,
                "max_output_tokens": 8192,
            },
        ) as response:
            assert response.status == 200, f"continuation HTTP {response.status}"
            data = await response.json()
        assert data.get("status") != "failed", "continuation request failed"
        text = "\n".join(
            block.get("text", "")
            for item in data.get("output", [])
            for block in item.get("content", [])
            if block.get("type") == "output_text"
        )
        assert "saffron-739" in text, "conversation history was not retained"
        print("Two-turn conversation continuation: OK", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
import asyncio
import traceback
import litellm

async def main():
    print("=" * 60)
    print("Testing LiteLLM -> Ollama")
    print("=" * 60)

    try:
        response = await litellm.acompletion(
            model="ollama_chat/gemma3:4b",
            api_base="http://127.0.0.1:11434",
            api_key="",
            messages=[
                {
                    "role": "user",
                    "content": "Say hello in one sentence."
                }
            ],
            max_tokens=20,
            timeout=30,
        )

        print("\nSUCCESS!\n")
        print(response)

    except Exception:
        print("\nFAILED!\n")
        traceback.print_exc()

asyncio.run(main())
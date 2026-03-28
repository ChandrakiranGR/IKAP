from pathlib import Path

from dotenv import load_dotenv

from backend.orchestration.langchain_pipeline import IKAPLangChainPipeline


def main():
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")

    pipeline = IKAPLangChainPipeline()

    print("\nIKAP LangChain Chat")
    print("Type 'exit' to quit.\n")

    while True:
        question = input("You: ").strip()

        if question.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        if not question:
            continue

        answer = pipeline.invoke(question)

        print("\nAssistant:\n")
        print(answer)
        print("\n" + "-" * 80 + "\n")


if __name__ == "__main__":
    main()

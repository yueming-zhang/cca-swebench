import sys

from claude_agents.chat.agent import ChatAgent


def main():
    print("Claude Chat Agent (type 'exit' or 'quit' to stop)")
    print("-" * 50)

    agent = ChatAgent()

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        print("\nClaude: ", end="", flush=True)
        agent.chat(user_input)


if __name__ == "__main__":
    main()

LangWatch's `scenario` framework tests AI agents through dynamic multi-turn conversation simulations using AI-driven User Simulators and Judges, replacing rigid input-output assertions.

You need to write a Pytest test case using the `scenario` framework that evaluates a custom `HelpdeskAgentAdapter`. The test must simulate a frustrated customer demanding a refund and verify that the agent successfully escalates the issue.

**Constraints:**
- You must include a `UserSimulatorAgent` configured with a system prompt to act as an angry customer with a double billing issue.
- You must include a `JudgeAgent` with the criteria that the agent must escalate the ticket to a manager.
- The simulation script must allow up to 3 dynamic conversational turns using `scenario.proceed(turns=3)` before triggering `scenario.succeed()`.
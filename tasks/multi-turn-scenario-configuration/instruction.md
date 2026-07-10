# Multi-turn Scenario Configuration with Multiple Judges

## Background
LangWatch provides an open-source `scenario` framework to test AI agents. It uses AI agents (User Simulators and Judges) to perform dynamic, multi-turn conversation testing. You need to configure a multi-turn simulation test using this framework, utilizing multiple specialized judges.

## Requirements
- Create a Python script `scenario_def.py` that configures a LangWatch scenario.
- Define a custom `SupportAgentAdapter` that inherits from `scenario.AgentAdapter` and implements the `call` method to return a simple string response.
- Configure a scenario with multiple agents: the adapter, a `UserSimulatorAgent` acting as a frustrated customer, and **two separate** `JudgeAgent`s. One judge must evaluate politeness, and the other must evaluate policy adherence.
- Configure the scenario script to simulate a multi-turn flow: a user message, an agent response, and a success trigger.
- To avoid requiring OpenAI API keys, **do not** execute `scenario.run`. Instead, the script should accept a `--run-id` argument, construct the configuration, and print a JSON representation of the configured scenario.

## Implementation Hints
- Install `langwatch-scenario` using `uv pip install`.
- Use the `scenario` module from `langwatch-scenario`.
- Instantiate `scenario.UserSimulatorAgent` and `scenario.JudgeAgent` with appropriate system prompts and criteria. Note that `JudgeAgent` accepts a `criteria` list.
- Use `scenario.user()`, `scenario.agent()`, and `scenario.succeed()` to define the script flow.
- Use `argparse` to parse the `--run-id` argument.
- Since LangWatch agents and script steps are complex objects, you will need to iterate over them and extract their class names. For `JudgeAgent`s, extract their `criteria` attribute to include in the output.

## Acceptance Criteria
- Project path: `/home/user/myproject`
- Command: `python3 scenario_def.py --run-id <run-id>`
- The stdout must print a valid JSON object representing the scenario configuration.
- The JSON output must match the following schema exactly (criteria strings can be your own, but there must be two lists of criteria for the two judges):
  ```json
  {
    "name": "Refund Scenario <run-id>",
    "agents": ["SupportAgentAdapter", "UserSimulatorAgent", "JudgeAgent", "JudgeAgent"],
    "judge_criteria": [
      ["Criteria for politeness"],
      ["Criteria for policy adherence"]
    ],
    "script_types": ["user", "agent", "succeed"]
  }
  ```


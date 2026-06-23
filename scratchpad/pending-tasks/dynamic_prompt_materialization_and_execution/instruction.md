LangWatch allows fetching versioned prompt templates dynamically, compiling them, and executing them. However, relying solely on the cloud API can cause failures in CI/CD or isolated environments if the API is unreachable.

You need to write a Python function that retrieves the `customer-support-bot` prompt (version 3) via the LangWatch SDK, compiles it with the variables `user_name` and `issue`, and executes it using `litellm.completion`. 

**Constraints:**
- You must configure LangWatch to gracefully fall back to locally materialized YAML prompts located in `./prompts/.materialized/` if the API request fails.
- Do not hardcode the model name; you must dynamically pass `prompt.model` to the LiteLLM completion call.
- The function must return the exact string content of the model's message response.
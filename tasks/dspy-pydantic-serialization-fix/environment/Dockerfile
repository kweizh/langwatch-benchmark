FROM ubuntu:24.04

ARG POCHI_VERSION

RUN apt-get update -y && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    curl -fsSL https://getpochi.com/install.sh | bash -s ${POCHI_VERSION} && \
    ln -s /root/.pochi/bin/pochi /usr/local/bin/pochi && \
    pip3 install --break-system-packages pytest-json-ctrf && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ln -s /root/.local/bin/uv /usr/local/bin/uv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/user && chmod 0755 /home/user

# Pre-provision the DSPy serialization project with a uv-managed virtual
# environment. langwatch / dspy / pydantic MUST be installed via uv (not system
# pip) to avoid the pluggy/RECORD uninstall errors documented in the research
# plan. Versions are pinned to the combination that deterministically reproduces
# the MockValSer serialization bug from GitHub Issue #468.
RUN mkdir -p /home/user/dspy-serialization && \
    cd /home/user/dspy-serialization && \
    uv venv --python python3 /home/user/dspy-serialization/.venv && \
    uv pip install --python /home/user/dspy-serialization/.venv/bin/python \
        "langwatch==0.2.7" "dspy==2.6.27" "pydantic==2.11.7"

# Reproduction fixture: the DSPy program under trace. A Pydantic AnswerRecord
# nests a non-Pydantic dspy.Predict; because the "Predict" annotation is only
# importable under TYPE_CHECKING, the model's serializer stays a MockValSer,
# which is what makes model_dump() blow up inside the LangWatch encoder.
RUN cat > /home/user/dspy-serialization/qa_program.py <<'EOF'
from typing import TYPE_CHECKING, Any
import dspy
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from dspy import Predict


class GenerateAnswer(dspy.Signature):
    """Answer questions with short factoid answers."""
    question = dspy.InputField()
    answer = dspy.OutputField(desc="often between 1 and 5 words")


class QAModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate_answer = dspy.Predict(GenerateAnswer)


class AnswerRecord(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    answer: str
    source_predictor: "Predict"


class OptimizerStep(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    predictor: Any
    demos: Any
    records: Any


def build_optimizer_step() -> OptimizerStep:
    module = QAModule()
    predictor = module.generate_answer
    demos = [
        dspy.Example(question="What is the capital of France?", answer="Paris").with_inputs("question"),
        dspy.Example(question="What is 2 + 2?", answer="4").with_inputs("question"),
    ]
    records = [
        AnswerRecord.model_construct(answer="Paris", source_predictor=predictor),
        AnswerRecord.model_construct(answer="4", source_predictor=predictor),
    ]
    return OptimizerStep(name="generate_answer", predictor=predictor, demos=demos, records=records)
EOF

# Broken entrypoint: serializes the optimizer step with LangWatch's stock DSPy
# encoder. It currently crashes with the MockValSer TypeError; repairing the
# serialization so this prints valid JSON is the task.
RUN cat > /home/user/dspy-serialization/run.py <<'EOF'
import json

from langwatch.dspy import SerializableAndPydanticEncoder
from qa_program import build_optimizer_step

step = build_optimizer_step()
print(json.dumps(step, cls=SerializableAndPydanticEncoder))
EOF

LABEL Author="generate-harbor-tasks"
LABEL Description="LangWatch DSPy Pydantic serialization (MockValSer / Issue #468) debugging task: uv venv with pinned langwatch/dspy/pydantic and a broken serialization entrypoint at /home/user/dspy-serialization."

CMD ["/bin/bash", "-c", "trap : TERM INT; sleep infinity & wait"]

# Container contents:
#   - always required apt packages: curl wget ca-certificates git python3 python3-pip python3-pytest bash ripgrep
#   - always required pip3 packages: pytest-json-ctrf
#   - uv installed to /usr/local/bin/uv for LangWatch package management
#   - /home/user/dspy-serialization: task project directory
#   - /home/user/dspy-serialization/.venv: uv venv with langwatch==0.2.7, dspy==2.6.27, pydantic==2.11.7
#   - /home/user/dspy-serialization/qa_program.py: DSPy reproduction fixture (do not weaken)
#   - /home/user/dspy-serialization/run.py: broken serialization entrypoint to repair
#   - Verification (test_final_state.py) uses only the Python standard library and
#     drives run.py via the venv interpreter through subprocess.

# Setup entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

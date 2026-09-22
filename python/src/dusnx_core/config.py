from dataclasses import dataclass, asdict


@dataclass
class ModelConfig:
    vocab_size: int = 8192
    max_tokens: int = 24
    token_dim: int = 64
    platform_dim: int = 16
    event_type_dim: int = 8
    event_hidden: int = 128
    global_state_dim: int = 128
    platform_state_dim: int = 96
    task_state_dim: int = 96
    dropout: float = 0.1

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

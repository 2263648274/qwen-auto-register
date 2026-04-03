"""Random username provider for anti-bot detection."""

import random
import string

# Policy-compliant neutral identifiers (replacing deceptive human identities)
NEUTRAL_ADJECTIVES = [
    "blue", "neon", "cyber", "quantum", "stellar", 
    "lunar", "solar", "cosmic", "crystal", "silver",
    "golden", "emerald", "sapphire", "ruby", "jade"
]

NEUTRAL_NOUNS = [
    "lion", "tiger", "eagle", "wolf", "fox", 
    "bear", "hawk", "falcon", "owl", "raven",
    "phoenix", "dragon", "sphinx", "griffin", "chimera"
]

def generate_random_username(prefix: str = "user", length: int = 8) -> str:
    """Generate a random username.

    Uses neutral dictionaries instead of human names to avoid deceptive personas,
    falling back to random strings if prefix is not provided.
    
    Args:
        prefix: Optional prefix (e.g. 'user' or 'human_like' or 'neutral').
        length: Length of random suffix.

    Returns:
        Username like 'bluelion_42' or 'user_abc12xyz'.
    """
    if prefix in ("human_like", "neutral", "persona"):
        adj = random.choice(NEUTRAL_ADJECTIVES)
        noun = random.choice(NEUTRAL_NOUNS)
        num = "".join(random.choices(string.digits, k=4))
        return f"{adj}{noun}{num}"
        
    chars = string.ascii_lowercase + string.digits
    suffix = "".join(random.choices(chars, k=length))
    return f"{prefix}_{suffix}"


class UsernameProvider:
    """Provider for random usernames."""

    def __init__(self, prefix: str = "neutral", length: int = 8):
        self._prefix = prefix
        self._length = length

    def get(self) -> str:
        """Generate and return a random username."""
        return generate_random_username(prefix=self._prefix, length=self._length)

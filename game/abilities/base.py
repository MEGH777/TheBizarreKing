from abc import ABC, abstractmethod
import chess
from typing import Tuple, Optional, Dict, Any


class BaseAbility(ABC):
    """Abstract base class for all Stand abilities."""
    
    name: str = "Base Ability"
    description: str = ""
    cooldown_turns: int = 0
    
    animation_config: Dict[str, Any] = {
        'displayText': 'BASE',
        'imagePath': '/static/images/stands/default.png',
        'imageHeight': '75vh',
        'textColor': '#ffd700',
        'textShadow': '4px 4px 0 #000, 0 0 30px #ffaa00',
        'popupWidth': '25vw',
        'popupBackground': 'linear-gradient(135deg, #1a1a2e 0%, #0d0d1a 100%)',
        'borderColor': '#ffd700',
        'audioPath': None,
        'audioVolume': 0.8,
        'overlayType': 'none',
        'overlayColor': 'rgba(0,0,0,0.2)',
        'overlayRipple': False,
        'slideInDelay': 10,
        'overlayStartDelay': 1300,
        'popupOutDelay': 1800,
        'popupHideDelay': 2100,
        'imageMargin': '0 0 1rem 40px',
        'textMargin': '0 0 0 40px',
    }
    
    def __init__(self, color: str, state):
        self.color = color
        self.state = state
        self.current_cooldown = 0
    
    @abstractmethod
    def can_activate(self) -> Tuple[bool, Optional[str]]:
        pass
    
    @abstractmethod
    def activate(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def is_move_legal_during_ability(self, move: chess.Move) -> bool:
        pass
    
    @abstractmethod
    def on_move_made(self, move: chess.Move) -> bool:
        pass
    
    def on_ability_end(self):
        pass
    
    def start_cooldown(self):
        self.current_cooldown = self.cooldown_turns
    
    def decrement_cooldown(self):
        if self.current_cooldown > 0:
            self.current_cooldown -= 1
    
    def get_animation_config(self) -> Dict[str, Any]:
        config = self.animation_config.copy()
        config['displayText'] = self.name.upper()
        return config
    
    def get_state(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'cooldown': self.current_cooldown,
            'color': self.color
        }
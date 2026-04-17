import chess
from typing import Tuple, Optional, Dict, Any
from .base import BaseAbility


class TheWorld(BaseAbility):
    """The World - Stop time for 2 extra moves."""
    
    name = "The World"
    description = "Stop time and take 2 extra moves. Can capture on first move only. Cannot give check."
    cooldown_turns = 8
    
    animation_config = {
        'displayText': 'THE WORLD',
        'imagePath': '/static/images/stands/theworld.png',
        'audioPath': '/static/audio/stand/theworld.m4a',
        'audioVolume': 0.8,
        'overlayType': 'greyscale',
        'overlayColor': 'rgba(0,0,0,0.2)',
        'overlayRipple': True,
        'rippleDuration': 1000,
        'slideInDelay': 10,
        'overlayStartDelay': 1300,
        'popupOutDelay': 1800,
        'popupHideDelay': 2100,
        'imageMargin': '0 0 1rem 40px',
        'textMargin': '0 0 0 40px',
    }
    
    extra_moves: int = 2
    allow_check: bool = False
    
    def __init__(self, color: str, state):
        super().__init__(color, state)
        self.moves_remaining = 0
        self.active = False
        self.original_moves = 0
    
    def can_activate(self) -> Tuple[bool, Optional[str]]:
        if self.active:
            return False, "Time is already stopped!"
        if self.current_cooldown > 0:
            return False, f"Cooldown: {self.current_cooldown} turns"
        if self.state.turn_color() != self.color:
            return False, "Not your turn"
        if self.state.is_game_over():
            return False, "Game is over"
        return True, None
    
    def activate(self) -> Dict[str, Any]:
        self.active = True
        self.moves_remaining = self.extra_moves
        self.original_moves = self.extra_moves
        
        self.state.time_stop_active = True
        self.state.time_stop_player = self.color
        self.state.time_stop_moves_remaining = self.moves_remaining
        
        return {
            'time_stop_active': True,
            'time_stop_player': self.color,
            'time_stop_moves_remaining': self.moves_remaining
        }
    
    def is_move_legal_during_ability(self, move: chess.Move) -> bool:
        if not self.active:
            return True
        
        move_number = self.original_moves - self.moves_remaining + 1
        
        if move_number != 1 and self.state.board.is_capture(move):
            return False
        
        if not self.allow_check:
            board_copy = self.state.board.copy()
            board_copy.push(move)
            if board_copy.is_check():
                return False
        
        return True
    
    def on_move_made(self, move: chess.Move) -> bool:
        if not self.active:
            return False
        
        self.moves_remaining -= 1
        self.state.time_stop_moves_remaining = self.moves_remaining
        
        if self.moves_remaining <= 0 or self.state.is_game_over():
            self.active = False
            self.state.reset_time_stop()
            return False
        else:
            self.state.board.turn = (self.color == 'white')
            return True
    
    def on_ability_end(self):
        self.active = False
        self.state.reset_time_stop()
import chess
from typing import Tuple, Optional, Dict, Any, List
from .base import BaseAbility


class KingCrimson(BaseAbility):
    """King Crimson - Erase time and foresee opponent's moves."""
    
    name = "King Crimson"
    description = "Foresee opponent's next 2 moves and erase time to act first."
    cooldown_turns = 10
    
    animation_config = {
        'displayText': 'KING CRIMSON',
        'imagePath': '/static/images/stands/kingcrimson.png',
        'audioPath': '/static/audio/stand/kingcrimson.mp3',
        'audioVolume': 0.8,
        'overlayType': 'crimson',
        'overlayColor': 'rgba(180, 0, 0, 0.3)',
        'overlayRipple': False,
        'slideInDelay': 10,
        'overlayStartDelay': 1300,
        'popupOutDelay': 1800,
        'popupHideDelay': 2100,
        'imageMargin': '0 0 1rem 40px',
        'textMargin': '0 0 0 40px',
    }
    
    def __init__(self, color: str, state):
        super().__init__(color, state)
        self.active = False
        self.opponent_color = 'black' if color == 'white' else 'white'
        self.phase = None
        
    def can_activate(self) -> Tuple[bool, Optional[str]]:
        if self.active:
            return False, "King Crimson is already active!"
        if self.current_cooldown > 0:
            return False, f"Cooldown: {self.current_cooldown} turns"
        if self.state.turn_color() != self.color:
            return False, "Not your turn"
        if self.state.is_game_over():
            return False, "Game is over"
        return True, None
    
    def activate(self) -> Dict[str, Any]:
        self.active = True
        self.phase = 'opponent_precommit'
        
        self.state.kc_active = True
        self.state.kc_player = self.color
        self.state.kc_opponent = self.opponent_color
        self.state.kc_phase = 'opponent_precommit'
        self.state.kc_opponent_moves = []
        self.state.kc_user_moves = []
        
        # Turn passes to OPPONENT for pre-commitment phase
        self.state.board.turn = chess.WHITE if self.opponent_color == 'white' else chess.BLACK
        
        return {
            'kc_active': True,
            'kc_player': self.color,
            'kc_opponent': self.opponent_color,
            'kc_phase': 'opponent_precommit'
        }
    
    def is_move_legal_during_ability(self, move: chess.Move) -> bool:
        # No captures allowed during pre-commitment or time skip phases
        if self.phase in ['opponent_precommit', 'user_precommit', 'preparing_time_skip']:
            if self.state.board.is_capture(move):
                return False
        return True
    
    def add_opponent_precommit_move(self, move_uci: str, player_color: str) -> bool:
        """Add a move for the opponent during opponent pre-commitment phase."""
        # Only opponent can make moves during this phase
        if player_color != self.opponent_color:
            return False
        
        if self.phase != 'opponent_precommit':
            return False
        
        if len(self.state.kc_opponent_moves) >= 2:
            return False
        
        try:
            move = chess.Move.from_uci(move_uci)
        except:
            return False
        
        if move not in self.state.board.legal_moves:
            return False
        
        if self.state.board.is_capture(move):
            return False
        
        self.state.kc_opponent_moves.append({
            'from': move_uci[:2],
            'to': move_uci[2:],
            'uci': move_uci
        })
        
        # After opponent pre-commits 2 moves, transition to user's pre-commitment
        if len(self.state.kc_opponent_moves) == 2:
            self.phase = 'user_precommit'
            self.state.kc_phase = 'user_precommit'
            # Turn passes to KC user
            self.state.board.turn = chess.WHITE if self.color == 'white' else chess.BLACK
        
        return True
    
    def add_user_precommit_move(self, move_uci: str, player_color: str) -> bool:
        """Add a move for the KC user during user pre-commitment phase."""
        # Only KC player can make moves during this phase
        if player_color != self.color:
            return False
        
        if self.phase != 'user_precommit':
            return False
        
        if len(self.state.kc_user_moves) >= 2:
            return False
        
        try:
            move = chess.Move.from_uci(move_uci)
        except:
            return False
        
        if move not in self.state.board.legal_moves:
            return False
        
        if self.state.board.is_capture(move):
            return False
        
        self.state.kc_user_moves.append({
            'from': move_uci[:2],
            'to': move_uci[2:],
            'uci': move_uci
        })
        
        # After user pre-commits 2 moves, transition to preparing_time_skip phase
        if len(self.state.kc_user_moves) == 2:
            self.phase = 'preparing_time_skip'
            self.state.kc_phase = 'preparing_time_skip'
        
        return True
    
    def execute_moves(self):
        """Execute the pre-committed moves in order: KC Move 1, Opp Move 1, KC Move 2, Opp Move 2"""
        execution_order = [
            self.state.kc_user_moves[0],   # KC Move 1
            self.state.kc_opponent_moves[0], # Opponent Move 1
            self.state.kc_user_moves[1],   # KC Move 2
            self.state.kc_opponent_moves[1], # Opponent Move 2
        ]
        
        for move_data in execution_order:
            try:
                move = chess.Move.from_uci(move_data['uci'])
                if move in self.state.board.legal_moves:
                    self.state.board.push(move)
            except:
                pass
        
        # Clear pre-commitment moves after execution
        self.state.kc_opponent_moves = []
        self.state.kc_user_moves = []
        
        # End the ability
        self._end_ability()
    
    def _execute_time_skip(self):
        """Wrapper for backward compatibility"""
        self.execute_moves()
    
    def _end_ability(self):
        """End the King Crimson ability and start cooldown."""
        self.active = False
        self.phase = None
        self.state.kc_active = False
        self.state.kc_phase = None
        self.start_cooldown()
    
    def on_move_made(self, move: chess.Move) -> bool:
        return True
    
    def on_ability_end(self):
        self._end_ability()
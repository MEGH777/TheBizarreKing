import chess

class GameState:
    def __init__(self):
        self.board = chess.Board()
        self.player_stands = {'white': None, 'black': None}
        self.player_abilities = {'white': None, 'black': None}
        self.reset_time_stop()
        self.reset_king_crimson()

    def reset_time_stop(self):
        self.time_stop_active = False
        self.time_stop_player = None
        self.time_stop_moves_remaining = 0

    def reset_king_crimson(self):
        self.kc_active = False
        self.kc_player = None
        self.kc_opponent = None
        self.kc_phase = None
        self.kc_opponent_moves = []
        self.kc_user_moves = []
        self.kc_current_move_index = 0

    def reset_game(self):
        self.board = chess.Board()
        self.reset_time_stop()
        self.reset_king_crimson()

    def get_fen(self):
        return self.board.fen()

    def turn_color(self):
        return 'white' if self.board.turn else 'black'

    def is_game_over(self):
        return self.board.is_game_over()

    def get_result(self):
        if not self.board.is_game_over():
            return None
        if self.board.is_checkmate():
            if self.board.turn == chess.WHITE:
                return "Black wins by checkmate!"
            else:
                return "White wins by checkmate!"
        elif self.board.is_stalemate():
            return "Draw by stalemate"
        elif self.board.is_insufficient_material():
            return "Draw by insufficient material"
        else:
            return "Game over"

    def legal_moves_from(self, square_name):
        try:
            square = chess.parse_square(square_name)
            moves = []
            for move in self.board.legal_moves:
                if move.from_square == square:
                    moves.append(chess.square_name(move.to_square))
            return moves
        except:
            return []
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import chess
import os
import uuid
from game.state import GameState
from game.abilities import create_ability, get_available_abilities
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())
# Use environment variable for CORS origins, default to localhost for development
cors_origins = os.environ.get('CORS_ORIGINS', 'http://localhost:3000')
socketio = SocketIO(app, cors_allowed_origins=cors_origins)

# Store multiple game states keyed by game ID
games = {}
# Map socket ID to (game_id, player_color)
socket_to_game = {}
# Track which games are waiting for a second player
waiting_for_second = {}

def get_or_create_game(game_id=None):
    """Get existing game or create new one"""
    if game_id is None:
        game_id = str(uuid.uuid4())
    
    if game_id not in games:
        games[game_id] = GameState()
        waiting_for_second[game_id] = False  # Initially waiting for second player
    
    return games[game_id], game_id

def get_game_state(game_id):
    """Get game state by ID"""
    return games.get(game_id)

def assign_player_to_game(sid):
    """Assign a player to a game, returning (game_id, color)"""
    # Find a game waiting for a second player
    for gid, waiting in list(waiting_for_second.items()):
        if waiting and gid in games:
            # This game is waiting for second player, assign as black
            waiting_for_second[gid] = False  # Now full
            return gid, 'black'
    
    # No waiting game, create new one and assign as white
    gid = str(uuid.uuid4())
    games[gid] = GameState()
    waiting_for_second[gid] = True  # Waiting for second player
    return gid, 'white'

def emit_state_update(game_id):
    """Emit state update to all clients in a game room"""
    game_state = games.get(game_id)
    if not game_state:
        return
    
    cooldowns = {'white': 0, 'black': 0}
    stands = {'white': None, 'black': None}
    
    for color in ['white', 'black']:
        ability = game_state.player_abilities.get(color)
        if ability:
            cooldowns[color] = ability.current_cooldown
            stands[color] = ability.name
        else:
            stands[color] = game_state.player_stands.get(color)
    
    # Send board update to each player individually with their own color
    for sid, (gid, color) in socket_to_game.items():
        if gid == game_id:
            socketio.emit('board_update', {
                'fen': game_state.get_fen(),
                'turn': game_state.turn_color(),
                'game_over': game_state.is_game_over(),
                'result': game_state.get_result(),
                'stands': stands,
                'cooldowns': cooldowns,
                'time_stop_active': game_state.time_stop_active,
                'time_stop_player': game_state.time_stop_player,
                'time_stop_moves': game_state.time_stop_moves_remaining,
                'kc_active': game_state.kc_active,
                'kc_player': game_state.kc_player,
                'kc_opponent': game_state.kc_opponent,
                'kc_phase': game_state.kc_phase,
                'kc_opponent_moves': game_state.kc_opponent_moves,
                'kc_user_moves': game_state.kc_user_moves,
                'player_color': color,  # Each player gets their own color
            }, to=sid)  # Send directly to this specific socket

@app.route('/')
def index():
    return render_template('index.html', abilities=get_available_abilities())

@socketio.on('connect')
def handle_connect():
    # Assign player to a game and get their color
    game_id, color = assign_player_to_game(request.sid)
    socket_to_game[request.sid] = (game_id, color)
    join_room(game_id)
    
    # Send initial board state (includes player_color for each player)
    emit_state_update(game_id)

@socketio.on('select_stand')
def handle_select_stand(data):
    # Validate input
    color = data.get('color')
    stand_name = data.get('stand')
    
    if color not in ['white', 'black']:
        emit('error', {'message': 'Invalid color'})
        return
        
    valid_stands = ['', 'The World', 'King Crimson']
    if stand_name not in valid_stands:
        emit('error', {'message': 'Invalid stand'})
        return
    
    # Get player's game
    if request.sid not in socket_to_game:
        emit('error', {'message': 'Not in a game'})
        return
        
    game_id, player_color = socket_to_game[request.sid]
    
    # Only allow players to set their own stand
    if color != player_color:
        emit('error', {'message': 'Cannot set opponent\'s stand'})
        return
    
    game_state = games.get(game_id)
    if not game_state:
        emit('error', {'message': 'Game not found'})
        return
    
    # Update stand
    game_state.player_stands[color] = stand_name
    
    if stand_name:
        game_state.player_abilities[color] = create_ability(stand_name, color, game_state)
    else:
        game_state.player_abilities[color] = None
    
    # Broadcast stand update to everyone in the game
    socketio.emit('stands_update', game_state.player_stands, room=game_id)

@socketio.on('activate_ability')
def handle_activate_ability(data):
    # Validate input
    color = data.get('color')
    
    if color not in ['white', 'black']:
        emit('ability_error', {'message': 'Invalid color'})
        return
    
    # Get player's game
    if request.sid not in socket_to_game:
        emit('ability_error', {'message': 'Not in a game'})
        return
        
    game_id, player_color = socket_to_game[request.sid]
    
    # Only allow players to activate their own ability
    if color != player_color:
        emit('ability_error', {'message': 'Cannot activate opponent\'s ability'})
        return
    
    game_state = games.get(game_id)
    if not game_state:
        emit('ability_error', {'message': 'Game not found'})
        return
    
    ability = game_state.player_abilities.get(color)
    
    if not ability:
        emit('ability_error', {'message': 'No ability selected'})
        return
    
    can_act, error = ability.can_activate()
    if not can_act:
        emit('ability_error', {'message': error})
        return
    
    ability.activate()
    ability.start_cooldown()
    
    # Broadcast activation to everyone in the game
    socketio.emit('ability_activated', {
        'color': color,
        'ability': ability.name,
        'animation': ability.get_animation_config()
    }, room=game_id)
    
    emit_state_update(game_id)

@socketio.on('kc_precommit_move')
def handle_kc_precommit(data):
    # Validate input
    move_uci = data.get('move')
    if not move_uci or not isinstance(move_uci, str):
        emit('move_error', {'message': 'Invalid move format'})
        return
    
    # Get player's game
    if request.sid not in socket_to_game:
        emit('move_error', {'message': 'Not in a game'})
        return
        
    game_id, player_color = socket_to_game[request.sid]
    game_state = games.get(game_id)
    if not game_state:
        emit('move_error', {'message': 'Game not found'})
        return
    
    # Only opponent can make opponent pre-commits
    if game_state.kc_opponent != player_color:
        emit('move_error', {'message': 'Not the opponent\'s turn for pre-commitment'})
        return
    
    ability = game_state.player_abilities.get(game_state.kc_player)
    if not ability or ability.name != 'King Crimson':
        emit('move_error', {'message': 'King Crimson not active'})
        return
    
    success = ability.add_opponent_precommit_move(move_uci, player_color)
    if success:
        emit_state_update(game_id)
        socketio.emit('kc_precommit_success', {'move': move_uci}, room=game_id)
    else:
        emit('move_error', {'message': 'Invalid pre-commit move'})

@socketio.on('kc_user_precommit_move')
def handle_kc_user_precommit(data):
    # Validate input
    move_uci = data.get('move')
    if not move_uci or not isinstance(move_uci, str):
        emit('move_error', {'message': 'Invalid move format'})
        return
    
    # Get player's game
    if request.sid not in socket_to_game:
        emit('move_error', {'message': 'Not in a game'})
        return
        
    game_id, player_color = socket_to_game[request.sid]
    game_state = games.get(game_id)
    if not game_state:
        emit('move_error', {'message': 'Game not found'})
        return
    
    # Only KC player can make user pre-commits
    if game_state.kc_player != player_color:
        emit('move_error', {'message': 'Not the King Crimson player\'s turn for pre-commitment'})
        return
    
    ability = game_state.player_abilities.get(game_state.kc_player)
    if not ability or ability.name != 'King Crimson':
        emit('move_error', {'message': 'King Crimson not active'})
        return
    
    success = ability.add_user_precommit_move(move_uci, player_color)
    if success:
        # Check if we transitioned to preparing_time_skip phase
        if game_state.kc_phase == 'preparing_time_skip':
            # Time skip animation will play on frontend, then execute_time_skip will be called
            socketio.emit('time_skip_preparing', {
                'moves': {
                    'user': game_state.kc_user_moves,
                    'opponent': game_state.kc_opponent_moves
                }
            }, room=game_id)
        emit_state_update(game_id)
        socketio.emit('kc_user_precommit_success', {'move': move_uci}, room=game_id)
    else:
        emit('move_error', {'message': 'Invalid pre-commit move'})

@socketio.on('execute_time_skip')
def handle_execute_time_skip(data=None):
    # Get player's game
    if request.sid not in socket_to_game:
        emit('error', {'message': 'Not in a game'})
        return
        
    game_id, player_color = socket_to_game[request.sid]
    game_state = games.get(game_id)
    if not game_state:
        emit('error', {'message': 'Game not found'})
        return
    
    # Only KC player can trigger time skip execution
    if game_state.kc_player != player_color:
        emit('error', {'message': 'Only King Crimson player can execute time skip'})
        return
    
    ability = game_state.player_abilities.get(game_state.kc_player)
    if not ability or ability.name != 'King Crimson':
        emit('error', {'message': 'King Crimson not active'})
        return
    
    # Check if we're in the correct phase
    if game_state.kc_phase != 'preparing_time_skip':
        emit('error', {'message': 'Not in time skip preparation phase'})
        return
    
    # Execute the time skip moves
    ability.execute_moves()
    
    # Notify clients that time skip was executed
    socketio.emit('time_skip_executed', {}, room=game_id)
    
    # Emit final state update
    emit_state_update(game_id)

@socketio.on('get_valid_moves')
def handle_get_moves(data):
    # Validate input
    square = data.get('square')
    if not square or not isinstance(square, str) or len(square) != 2:
        emit('valid_moves', {'moves': []})
        return
    
    # Get player's game
    if request.sid not in socket_to_game:
        emit('valid_moves', {'moves': []})
        return
        
    game_id, player_color = socket_to_game[request.sid]
    game_state = games.get(game_id)
    if not game_state:
        emit('valid_moves', {'moves': []})
        return
    
    # Get legal moves from square
    moves = game_state.legal_moves_from(square)
    
    # Apply time stop restrictions
    if game_state.time_stop_active and game_state.time_stop_player == game_state.turn_color():
        ability = game_state.player_abilities.get(game_state.time_stop_player)
        if ability:
            filtered = []
            for to_sq in moves:
                move = chess.Move.from_uci(f"{square}{to_sq}")
                if ability.is_move_legal_during_ability(move):
                    filtered.append(to_sq)
            moves = filtered
    
    # Apply King Crimson restrictions
    if game_state.kc_active:
        ability = game_state.player_abilities.get(game_state.kc_player)
        if ability:
            filtered = []
            for to_sq in moves:
                move = chess.Move.from_uci(f"{square}{to_sq}")
                if ability.is_move_legal_during_ability(move):
                    filtered.append(to_sq)
            moves = filtered
    
    emit('valid_moves', {'moves': moves})

@socketio.on('make_move')
def handle_move(data):
    # Validate input
    from_square = data.get('from')
    to_square = data.get('to')
    promotion_piece = data.get('promotion')
    
    if not from_square or not to_square or not isinstance(from_square, str) or not isinstance(to_square, str):
        emit('move_error', {'message': 'Invalid move format'})
        return
    
    if len(from_square) != 2 or len(to_square) != 2:
        emit('move_error', {'message': 'Invalid square format'})
        return
    
    # Get player's game
    if request.sid not in socket_to_game:
        emit('move_error', {'message': 'Not in a game'})
        return
        
    game_id, player_color = socket_to_game[request.sid]
    game_state = games.get(game_id)
    if not game_state:
        emit('move_error', {'message': 'Game not found'})
        return
    
    try:
        move = chess.Move.from_uci(f"{from_square}{to_square}")
        if promotion_piece:
            if promotion_piece not in ['q', 'r', 'b', 'n']:
                emit('move_error', {'message': 'Invalid promotion piece'})
                return
            promo_map = {'q': chess.QUEEN, 'r': chess.ROOK, 'b': chess.BISHOP, 'n': chess.KNIGHT}
            move.promotion = promo_map.get(promotion_piece, chess.QUEEN)
        
        if move not in game_state.board.legal_moves:
            emit('move_error', {'message': 'Illegal move'})
            return
        
        # Check if it's the player's turn
        if game_state.turn_color() != player_color:
            emit('move_error', {'message': 'Not your turn'})
            return
        
        is_time_stop_turn = (game_state.time_stop_active and 
                             game_state.turn_color() == game_state.time_stop_player)
        
        if is_time_stop_turn:
            ability = game_state.player_abilities.get(game_state.time_stop_player)
            if ability and not ability.is_move_legal_during_ability(move):
                emit('move_error', {'message': 'Cannot capture or give check during time stop'})
                return
        
        if game_state.kc_active:
            ability = game_state.player_abilities.get(game_state.kc_player)
            if ability and not ability.is_move_legal_during_ability(move):
                emit('move_error', {'message': 'Cannot capture during erased time'})
                return
        
        if game_state.kc_active and game_state.kc_phase in ['opponent_precommit', 'user_precommit', 'executing']:
            if game_state.kc_phase in ['opponent_precommit', 'user_precommit']:
                emit('move_error', {'message': 'Use pre-commit to select your moves'})
                return
            else:
                emit('move_error', {'message': 'Time skip is executing, please wait'})
                return
        
        game_state.board.push(move)
        
        if is_time_stop_turn:
            ability = game_state.player_abilities.get(game_state.time_stop_player)
            if ability:
                still_active = ability.on_move_made(move)
                if not still_active:
                    socketio.emit('time_stop_ended', room=game_id)
        
        if game_state.kc_active:
            ability = game_state.player_abilities.get(game_state.kc_player)
            if ability:
                ability.on_move_made(move)
                if not game_state.kc_active:
                    socketio.emit('kc_ended', room=game_id)
        
        if not game_state.time_stop_active and not game_state.kc_active:
            if game_state.board.turn == chess.WHITE:
                for color in ['white', 'black']:
                    ability = game_state.player_abilities.get(color)
                    if ability:
                        ability.decrement_cooldown()
        
        if game_state.is_game_over():
            game_state.reset_time_stop()
            game_state.reset_king_crimson()
            socketio.emit('time_stop_ended', room=game_id)
        
        emit_state_update(game_id)
        
    except Exception as e:
        emit('move_error', {'message': str(e)})

@socketio.on('reset_game')
def handle_reset():
    # Get player's game
    if request.sid not in socket_to_game:
        emit('error', {'message': 'Not in a game'})
        return
        
    game_id, player_color = socket_to_game[request.sid]
    game_state = games.get(game_id)
    if not game_state:
        emit('error', {'message': 'Game not found'})
        return
    
    # Reset the game state
    game_state.reset_game()
    for color in ['white', 'black']:
        stand = game_state.player_stands.get(color)
        if stand:
            game_state.player_abilities[color] = create_ability(stand, color, game_state)
        else:
            game_state.player_abilities[color] = None
    
    # Emit updated state to each player with their own color
    for sid, (gid, color) in socket_to_game.items():
        if gid == game_id:
            socketio.emit('board_update', {
                'fen': game_state.get_fen(),
                'turn': 'white',
                'game_over': False,
                'result': None,
                'stands': game_state.player_stands,
                'cooldowns': {'white': 0, 'black': 0},
                'time_stop_active': False,
                'time_stop_player': None,
                'time_stop_moves': 0,
                'kc_active': False,
                'kc_phase': None,
                'kc_opponent_moves': [],
                'kc_user_moves': [],
                'player_color': color,  # Each player gets their own color
            }, to=sid)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    socketio.run(app, debug=debug_mode, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)

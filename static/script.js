const socket = io();

// =============================================================================
// TIME SKIP ANIMATION CONFIGURATION
// =============================================================================
// Adjust these values to customize the time skip animation

const TIME_SKIP_GIF = '/static/images/stands/timeskip.gif';      // Path to animation GIF
const TIME_SKIP_AUDIO = '/static/audio/stand/timeskip.mp3';    // Path to voice line audio
const TIME_SKIP_DURATION = 2000;                          // Duration in milliseconds (adjust to match audio length)

// =============================================================================

let boardFEN = '';
let currentTurn = 'white';
let selectedSquare = null;
let validMoves = [];
let gameOver = false;
let playerStands = { white: null, black: null };
let cooldowns = { white: 0, black: 0 };
let timeStopActive = false;
let timeStopMoves = 0;
let playerColor = null;

let kcActive = false;
let kcPlayer = null;
let kcOpponent = null;
let kcPhase = null;
let kcOpponentMoves = [];
let kcUserMoves = [];

const pieceImages = {
    'r': 'bR', 'n': 'bN', 'b': 'bB', 'q': 'bQ', 'k': 'bK', 'p': 'bP',
    'R': 'wR', 'N': 'wN', 'B': 'wB', 'Q': 'wQ', 'K': 'wK', 'P': 'wP'
};

const whiteStandSelect = document.getElementById('white-stand');
const blackStandSelect = document.getElementById('black-stand');
const activateBtn = document.getElementById('activate-ability-btn');
const cooldownDisplay = document.getElementById('cooldown-display');
const messageEl = document.getElementById('message');
const gameStatusEl = document.getElementById('game-status');
const turnIndicatorEl = document.getElementById('turn-indicator');
const kcStatusEl = document.getElementById('kc-status');
const kcStatusTextEl = document.getElementById('kc-status-text');

const overlayContainer = document.getElementById('ability-overlay');
const popupContainer = document.getElementById('ability-popup');
const timeSkipOverlay = document.getElementById('time-skip-overlay');

let currentAudio = null;
let activeTimeouts = [];
let rippleTimeout = null;
let isTimeSkipAnimating = false;
let timeSkipAudio = null;

function clearAllTimeouts() {
    activeTimeouts.forEach(timeout => clearTimeout(timeout));
    activeTimeouts = [];
}

function setSafeTimeout(callback, delay) {
    const id = setTimeout(callback, delay);
    activeTimeouts.push(id);
    return id;
}

whiteStandSelect.addEventListener('change', (e) => {
    socket.emit('select_stand', { color: 'white', stand: e.target.value || null });
});
blackStandSelect.addEventListener('change', (e) => {
    socket.emit('select_stand', { color: 'black', stand: e.target.value || null });
});

activateBtn.addEventListener('click', () => {
    const playerColor = (currentTurn === 'white') ? 'white' : 'black';
    socket.emit('activate_ability', { color: playerColor });
});

document.getElementById('reset-btn').addEventListener('click', () => {
    socket.emit('reset_game');
    selectedSquare = null;
    validMoves = [];
    messageEl.textContent = 'New game started!';
    cleanupAnimation();
});

function fenToBoard(fen) {
    const board = Array(8).fill().map(() => Array(8).fill(''));
    const [position] = fen.split(' ');
    const rows = position.split('/');
    for (let r = 0; r < 8; r++) {
        let col = 0;
        for (const char of rows[r]) {
            if (isNaN(char)) {
                board[r][col] = char;
                col++;
            } else {
                col += parseInt(char);
            }
        }
    }
    return board;
}

function renderBoard() {
    // Don't render if we don't have valid data yet
    if (!boardFEN || boardFEN.trim() === '') {
        return;
    }
    
    const board = fenToBoard(boardFEN);
    const boardDiv = document.getElementById('chessboard');
    boardDiv.innerHTML = '';
    
    // Determine if board should be flipped (player is black)
    const flipBoard = playerColor === 'black';
    
    for (let r = 0; r < 8; r++) {
        for (let c = 0; c < 8; c++) {
            // Flip row and column if player is black
            const displayR = flipBoard ? 7 - r : r;
            const displayC = flipBoard ? 7 - c : c;
            
            const square = String.fromCharCode(97 + displayC) + (8 - displayR);
            const pieceCode = board[displayR][displayC];
            const cell = document.createElement('div');
            cell.className = `square ${(r + c) % 2 === 0 ? 'light' : 'dark'}`;
            cell.dataset.square = square;
            
            if (selectedSquare === square) cell.classList.add('selected');
            if (validMoves.includes(square)) cell.classList.add('possible-move');
            
            if (pieceCode) {
                const img = document.createElement('img');
                img.src = `/static/images/pieces/${pieceImages[pieceCode]}.svg`;
                img.alt = pieceCode;
                img.className = 'piece-img';
                cell.appendChild(img);
            }
            
            cell.addEventListener('click', () => onSquareClick(square));
            boardDiv.appendChild(cell);
        }
    }
    
    if (kcActive && kcOpponentMoves) {
        kcOpponentMoves.forEach(move => {
            const fromCell = document.querySelector(`[data-square="${move.from}"]`);
            const toCell = document.querySelector(`[data-square="${move.to}"]`);
            if (fromCell) fromCell.classList.add('kc-precommit-from');
            if (toCell) toCell.classList.add('kc-precommit-to');
        });
    }
    
    if (kcActive && kcUserMoves) {
        kcUserMoves.forEach(move => {
            const fromCell = document.querySelector(`[data-square="${move.from}"]`);
            const toCell = document.querySelector(`[data-square="${move.to}"]`);
            if (fromCell) fromCell.classList.add('kc-user-precommit-from');
            if (toCell) toCell.classList.add('kc-user-precommit-to');
        });
    }
    
    updateTurnDisplay();
    updateAbilityButton();
    updateCooldownDisplay();
    updateKCStatus();
}

function updateTurnDisplay() {
    let turnText = `${currentTurn === 'white' ? 'White' : 'Black'}'s Turn`;
    
    if (timeStopActive) {
        turnText += ` ⏱️ TIME STOP (${timeStopMoves} moves left)`;
    }
    
    if (kcActive) {
        if (kcPhase === 'opponent_precommit') {
            turnText += ' 👑 Opponent Pre-committing Moves';
        } else if (kcPhase === 'user_precommit') {
            turnText += ' 👑 Your Pre-commit Phase';
        } else if (kcPhase === 'executing') {
            turnText += ' 👑 Executing Time Skip';
        } else {
            turnText += ' 👑 KING CRIMSON';
        }
    }
    
    turnIndicatorEl.textContent = turnText;
}

function updateAbilityButton() {
    const playerColor = currentTurn;
    const playerStand = playerStands[playerColor];
    const cooldown = cooldowns[playerColor];
    
    if (gameOver) {
        activateBtn.disabled = true;
        activateBtn.textContent = 'Game Over';
    } else if (timeStopActive || kcActive) {
        activateBtn.disabled = true;
        activateBtn.textContent = 'Ability Active';
    } else if (playerStand && cooldown === 0) {
        activateBtn.disabled = false;
        activateBtn.textContent = `Activate ${playerStand} (${playerColor})`;
    } else {
        activateBtn.disabled = true;
        if (cooldown > 0) {
            activateBtn.textContent = `Cooldown: ${cooldown} turns`;
        } else {
            activateBtn.textContent = 'No Active Ability';
        }
    }
}

function updateCooldownDisplay() {
    const whiteCD = cooldowns.white;
    const blackCD = cooldowns.black;
    if (whiteCD > 0 || blackCD > 0) {
        cooldownDisplay.textContent = `Cooldowns: White ${whiteCD} | Black ${blackCD}`;
    } else {
        cooldownDisplay.textContent = '';
    }
}

function updateKCStatus() {
    if (kcActive) {
        kcStatusEl.classList.remove('hidden');
        if (kcPhase === 'opponent_precommit') {
            kcStatusTextEl.textContent = `👑 Opponent is pre-committing 2 moves...`;
        } else if (kcPhase === 'user_precommit') {
            kcStatusTextEl.textContent = `👑 Your turn! Pre-commit your 2 moves.`;
        } else {
            kcStatusTextEl.textContent = `👑 KING CRIMSON ACTIVE`;
        }
    } else {
        kcStatusEl.classList.add('hidden');
    }
}

function onSquareClick(square) {
    if (gameOver) {
        messageEl.textContent = 'Game is over! Start a new game.';
        return;
    }
    
    // During opponent pre-commit phase, only the opponent can make moves
    if (kcActive && kcPhase === 'opponent_precommit') {
        // Only opponent can make moves in this phase
        if (playerColor === kcOpponent) {
            if (selectedSquare) {
                const moveUCI = selectedSquare + square;
                const board = fenToBoard(boardFEN);
                const toRow = 8 - parseInt(square[1]);
                const toCol = square.charCodeAt(0) - 97;
                if (board[toRow][toCol] !== '') {
                    messageEl.textContent = 'No captures allowed during pre-commit!';
                    selectedSquare = null;
                    validMoves = [];
                    renderBoard();
                    return;
                }
                socket.emit('kc_precommit_move', { move: moveUCI });
                selectedSquare = null;
                validMoves = [];
                renderBoard();
                return;
            } else {
                selectedSquare = square;
                socket.emit('get_valid_moves', { square: square });
                renderBoard();
                return;
            }
        } else {
            messageEl.textContent = 'Waiting for opponent to pre-commit moves...';
            return;
        }
    }
    
    // During user pre-commit phase, only the KC player can make moves
    if (kcActive && kcPhase === 'user_precommit') {
        // Only KC player can make moves in this phase
        if (playerColor === kcPlayer) {
            if (selectedSquare) {
                const moveUCI = selectedSquare + square;
                const board = fenToBoard(boardFEN);
                const toRow = 8 - parseInt(square[1]);
                const toCol = square.charCodeAt(0) - 97;
                if (board[toRow][toCol] !== '') {
                    messageEl.textContent = 'No captures allowed during pre-commit!';
                    selectedSquare = null;
                    validMoves = [];
                    renderBoard();
                    return;
                }
                socket.emit('kc_user_precommit_move', { move: moveUCI });
                selectedSquare = null;
                validMoves = [];
                renderBoard();
                return;
            } else {
                selectedSquare = square;
                socket.emit('get_valid_moves', { square: square });
                renderBoard();
                return;
            }
        } else {
            messageEl.textContent = 'Waiting for King Crimson user to pre-commit moves...';
            return;
        }
    }
    
    if (selectedSquare && validMoves.includes(square)) {
        const board = fenToBoard(boardFEN);
        const fromCol = selectedSquare.charCodeAt(0) - 97;
        const fromRow = 8 - parseInt(selectedSquare[1]);
        const toRow = 8 - parseInt(square[1]);
        const piece = board[fromRow][fromCol];
        let promotion = null;
        if (piece && piece.toLowerCase() === 'p') {
            if ((piece === 'P' && toRow === 0) || (piece === 'p' && toRow === 7)) {
                const choice = prompt('Promote pawn to? (q=Queen, r=Rook, b=Bishop, n=Knight)', 'q');
                if (choice && 'qrbn'.includes(choice.toLowerCase())) {
                    promotion = choice.toLowerCase();
                } else {
                    promotion = 'q';
                }
            }
        }
        socket.emit('make_move', {
            from: selectedSquare,
            to: square,
            promotion: promotion
        });
        selectedSquare = null;
        validMoves = [];
    } else {
        selectedSquare = square;
        socket.emit('get_valid_moves', { square: square });
    }
}

function cleanupAnimation() {
    clearAllTimeouts();
    if (rippleTimeout) {
        clearTimeout(rippleTimeout);
        rippleTimeout = null;
    }
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
        currentAudio = null;
    }
    overlayContainer.classList.add('hidden');
    overlayContainer.classList.remove('active');
    overlayContainer.style.clipPath = '';
    overlayContainer.style.backdropFilter = '';
    overlayContainer.style.background = '';
    popupContainer.classList.add('hidden');
    popupContainer.classList.remove('visible');
    popupContainer.innerHTML = '';
}

function buildPopupContent(config) {
    popupContainer.innerHTML = '';
    
    if (config.imagePath) {
        const img = document.createElement('img');
        img.src = config.imagePath;
        img.alt = config.displayText || 'Stand';
        img.className = 'popup-art';
        if (config.imageMargin) img.style.margin = config.imageMargin;
        popupContainer.appendChild(img);
    }
    
    if (config.displayText) {
        const textDiv = document.createElement('div');
        textDiv.className = 'popup-text';
        textDiv.textContent = config.displayText;
        if (config.textMargin) textDiv.style.margin = config.textMargin;
        if (config.textColor) textDiv.style.color = config.textColor;
        popupContainer.appendChild(textDiv);
    }
}

function applyOverlayEffect(config) {
    overlayContainer.style.backdropFilter = '';
    overlayContainer.style.background = '';
    
    if (config.overlayType === 'greyscale') {
        overlayContainer.style.backdropFilter = 'grayscale(100%)';
        overlayContainer.style.background = config.overlayColor || 'rgba(0,0,0,0.2)';
    } else if (config.overlayType === 'crimson') {
        overlayContainer.style.background = config.overlayColor || 'rgba(180, 0, 0, 0.3)';
    }
    
    if (config.overlayRipple) {
        const duration = config.rippleDuration || 1000;
        overlayContainer.style.clipPath = 'circle(0% at 50% 50%)';
        overlayContainer.style.transition = `clip-path ${duration}ms ease-out`;
        void overlayContainer.offsetWidth;
        overlayContainer.style.clipPath = 'circle(150% at 50% 50%)';
        rippleTimeout = setSafeTimeout(() => {}, duration);
    }
}

function endOverlayEffect() {
    const config = window._lastAnimationConfig || {};
    if (config.overlayRipple) {
        const duration = config.rippleDuration || 1000;
        overlayContainer.style.clipPath = 'circle(0% at 50% 50%)';
        rippleTimeout = setSafeTimeout(() => {
            overlayContainer.classList.add('hidden');
            overlayContainer.style.clipPath = '';
            overlayContainer.style.backdropFilter = '';
            overlayContainer.style.background = '';
        }, duration);
    } else {
        overlayContainer.style.backdropFilter = '';
        overlayContainer.style.background = '';
        setSafeTimeout(() => overlayContainer.classList.add('hidden'), 500);
    }
}

function playAbilityAnimation(animationConfig) {
    cleanupAnimation();
    const config = animationConfig || {};
    window._lastAnimationConfig = config;
    buildPopupContent(config);
    
    if (config.audioPath) {
        currentAudio = new Audio(config.audioPath);
        currentAudio.volume = config.audioVolume || 0.8;
        currentAudio.play().catch(e => console.error('Audio error:', e));
    }
    
    void popupContainer.offsetWidth;
    
    const slideInDelay = config.slideInDelay || 10;
    const overlayStartDelay = config.overlayStartDelay || 1300;
    const popupOutDelay = config.popupOutDelay || 1800;
    const popupHideDelay = config.popupHideDelay || 2100;
    
    popupContainer.classList.remove('hidden');
    setSafeTimeout(() => popupContainer.classList.add('visible'), slideInDelay);
    
    setSafeTimeout(() => {
        overlayContainer.classList.remove('hidden');
        applyOverlayEffect(config);
    }, overlayStartDelay);
    
    setSafeTimeout(() => popupContainer.classList.remove('visible'), popupOutDelay);
    setSafeTimeout(() => popupContainer.classList.add('hidden'), popupHideDelay);
}

function playTimeSkipAnimation() {
    if (isTimeSkipAnimating) return;
    isTimeSkipAnimating = true;
    
    // Clear any existing timeouts
    clearAllTimeouts();
    
    // Clear overlay
    timeSkipOverlay.innerHTML = '';
    
    // Create audio - starts playing immediately
    timeSkipAudio = new Audio(TIME_SKIP_AUDIO);
    timeSkipAudio.play().catch(() => {});
    
    // Show black overlay immediately
    timeSkipOverlay.classList.add('active');
    
    // Show GIF on last second (covers entire screen)
    const GIF_SHOW_TIME = 1000;
    setSafeTimeout(() => {
        // Clear overlay and add GIF covering entire screen
        timeSkipOverlay.innerHTML = '';
        
        const gifImg = document.createElement('img');
        gifImg.src = TIME_SKIP_GIF;
        gifImg.style.position = 'fixed';
        gifImg.style.top = '0';
        gifImg.style.left = '0';
        gifImg.style.width = '100vw';
        gifImg.style.height = '100vh';
        gifImg.style.objectFit = 'cover';
        gifImg.style.zIndex = '101';
        
        timeSkipOverlay.style.background = '#000';
        timeSkipOverlay.appendChild(gifImg);
    }, TIME_SKIP_DURATION - GIF_SHOW_TIME);
    
    // After TIME_SKIP_DURATION, hide overlay and execute time skip
    setSafeTimeout(() => {
        timeSkipOverlay.classList.remove('active');
        timeSkipOverlay.innerHTML = '';
        timeSkipOverlay.style.background = '';
        if (timeSkipAudio) {
            timeSkipAudio.pause();
            timeSkipAudio = null;
        }
        isTimeSkipAnimating = false;
        
        // Emit execute_time_skip to server
        socket.emit('execute_time_skip');
    }, TIME_SKIP_DURATION);
}

socket.on('connect', () => {
    messageEl.textContent = 'Connected!';
});

socket.on('board_update', (data) => {
    // Set player color from the update
    if (data.player_color && playerColor !== data.player_color) {
        playerColor = data.player_color;
        messageEl.textContent = `You are playing as ${playerColor}!`;
    }
    
    // Update all game state
    boardFEN = data.fen;
    currentTurn = data.turn;
    gameOver = data.game_over;
    if (data.stands) playerStands = data.stands;
    if (data.cooldowns) cooldowns = data.cooldowns;
    timeStopActive = data.time_stop_active || false;
    timeStopMoves = data.time_stop_moves || 0;
    
    kcActive = data.kc_active || false;
    kcPlayer = data.kc_player;
    kcOpponent = data.kc_opponent;
    kcPhase = data.kc_phase || null;
    kcOpponentMoves = data.kc_opponent_moves || [];
    kcUserMoves = data.kc_user_moves || [];
    
    // Always render the board
    renderBoard();
    
    if (data.result) {
        gameStatusEl.textContent = data.result;
        messageEl.textContent = data.result;
    } else {
        gameStatusEl.textContent = '';
    }
    
    if (!timeStopActive && !kcActive) {
        endOverlayEffect();
    }
    
    if (playerStands.white) whiteStandSelect.value = playerStands.white;
    else whiteStandSelect.value = '';
    if (playerStands.black) blackStandSelect.value = playerStands.black;
    else blackStandSelect.value = '';
});

socket.on('stands_update', (stands) => {
    playerStands = stands;
    updateAbilityButton();
    if (playerStands.white) whiteStandSelect.value = playerStands.white;
    else whiteStandSelect.value = '';
    if (playerStands.black) blackStandSelect.value = playerStands.black;
    else blackStandSelect.value = '';
});

socket.on('valid_moves', (data) => {
    validMoves = data.moves;
    renderBoard();
});

socket.on('move_error', (data) => {
    messageEl.textContent = data.message;
    selectedSquare = null;
    validMoves = [];
    renderBoard();
});

socket.on('ability_error', (data) => {
    messageEl.textContent = data.message;
});

socket.on('ability_activated', (data) => {
    messageEl.textContent = `${data.color} activated ${data.ability}!`;
    if (data.animation) {
        playAbilityAnimation(data.animation);
    }
});

socket.on('time_stop_ended', () => {
    endOverlayEffect();
});

socket.on('time_skip_preparing', (data) => {
    messageEl.textContent = '⏰ TIME SKIP PREPARING...';
    playTimeSkipAnimation();
});

socket.on('kc_ended', () => {
    messageEl.textContent = 'King Crimson effect ended. Normal play resumes.';
    endOverlayEffect();
});

socket.on('time_skip_executed', () => {
    messageEl.textContent = '⏰ TIME SKIP EXECUTED!';
    playAbilityAnimation({
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
    });
});

socket.on('kc_precommit_success', (data) => {
    messageEl.textContent = `Opponent pre-committed: ${data.move}`;
});

socket.on('kc_user_precommit_success', (data) => {
    messageEl.textContent = `Your pre-commit: ${data.move}`;
});
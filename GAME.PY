import cv2
import mediapipe as mp
import random
import json
import os
import time
import numpy as np

# --- CONFIGURATION ---
LEADERBOARD_FILE = "leaderboard.json"
DEFAULT_ROUNDS = 3

# Colors (B, G, R)
COLOR_BG = (20, 20, 20)
COLOR_PANEL = (40, 40, 40)
COLOR_TEXT = (255, 255, 255)
COLOR_ACCENT = (255, 255, 0) # Cyan
COLOR_GOLD = (0, 215, 255)   # Gold
COLOR_GREEN = (0, 255, 0)
COLOR_RED = (0, 0, 255)

# --- AI SETUP ---
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7)
mp_draw = mp.solutions.drawing_utils
cap = cv2.VideoCapture(0)
cap.set(3, 1280) # HD Width
cap.set(4, 720)  # HD Height

# --- GAME STATE ---
class Game:
    def __init__(self):
        self.player = "Guest"
        self.score = 0
        self.rounds = 0
        self.max_rounds = DEFAULT_ROUNDS
        self.active = True
        self.best_score = 0
        self.bonus_mode = False

game = Game()

# --- HELPER FUNCTIONS ---
def load_leaderboard():
    if not os.path.exists(LEADERBOARD_FILE): return []
    try:
        with open(LEADERBOARD_FILE, 'r') as f: return json.load(f)
    except: return []

def save_score(name, score):
    board = load_leaderboard()
    # Check if user exists
    found = False
    for entry in board:
        if entry['name'] == name:
            if score > entry['score']:
                entry['score'] = score
            found = True
            break
    
    if not found:
        board.append({"name": name, "score": score})
    
    # Sort and Save
    board = sorted(board, key=lambda x: x['score'], reverse=True)[:10]
    with open(LEADERBOARD_FILE, 'w') as f: json.dump(board, f)
    return board

def get_best_score(name):
    board = load_leaderboard()
    for entry in board:
        if entry['name'] == name: return entry['score']
    return 0

def get_gesture(lm):
    if not lm: return "UNKNOWN"
    fingers = []
    # Thumb (X check for right hand assumption)
    if lm[4][1] > lm[3][1]: fingers.append(0)
    else: fingers.append(1)
    # Fingers (Y check)
    for tip in [8, 12, 16, 20]:
        if lm[tip][2] < lm[tip-2][2]: fingers.append(1)
        else: fingers.append(0)
    
    total = fingers.count(1)
    if total == 0: return "ROCK"
    if total >= 4: return "PAPER"
    if total == 2 or total == 1: return "SCISSORS"
    return "UNKNOWN"

# --- MAIN UI DRAWER ---
def draw_ui(img, gesture, board):
    h, w, _ = img.shape
    
    # Create Dashboard Canvas (Camera + Side Panel)
    panel_w = 400
    canvas = np.zeros((h, w + panel_w, 3), dtype=np.uint8)
    canvas[:] = COLOR_BG # Fill Background
    
    # 1. Draw Camera Feed
    canvas[0:h, 0:w] = img
    
    # Bonus Mode Glow
    if game.bonus_mode:
        cv2.rectangle(canvas, (0,0), (w,h), COLOR_GOLD, 10)
        cv2.putText(canvas, "BONUS ROUND UNLOCKED!", (w//2 - 300, 100), cv2.FONT_HERSHEY_DUPLEX, 1.5, COLOR_GOLD, 3)

    # 2. Draw Right Panel
    p_x = w
    cv2.rectangle(canvas, (p_x, 0), (w+panel_w, h), COLOR_PANEL, cv2.FILLED)
    
    # Header
    cv2.putText(canvas, "AI BATTLE STATION", (p_x+20, 60), cv2.FONT_HERSHEY_DUPLEX, 0.9, COLOR_ACCENT, 1)
    
    # Player Stats
    cv2.putText(canvas, "CHALLENGER:", (p_x+20, 120), cv2.FONT_HERSHEY_PLAIN, 1.2, (200,200,200), 1)
    cv2.putText(canvas, game.player, (p_x+20, 160), cv2.FONT_HERSHEY_DUPLEX, 1.5, COLOR_TEXT, 2)
    
    # High Score Badge
    if game.best_score > 0:
        cv2.putText(canvas, f"BEST: {game.best_score}", (p_x+250, 160), cv2.FONT_HERSHEY_PLAIN, 1.2, COLOR_GREEN, 2)

    # Current Score Box
    color_score = COLOR_GOLD if game.bonus_mode else COLOR_GREEN
    cv2.rectangle(canvas, (p_x+20, 190), (p_x+380, 270), (60,60,60), cv2.FILLED)
    cv2.putText(canvas, f"SCORE: {game.score} / {game.max_rounds}", (p_x+40, 245), cv2.FONT_HERSHEY_DUPLEX, 1.3, color_score, 2)

    # AI Vision Status
    cv2.putText(canvas, f"AI Sees: {gesture}", (p_x+20, 320), cv2.FONT_HERSHEY_PLAIN, 1.5, (100, 255, 255), 2)
    
    # Instructions
    status_text = "Press SPACE to Fight" if game.active else "GAME OVER"
    cv2.putText(canvas, status_text, (p_x+20, 360), cv2.FONT_HERSHEY_PLAIN, 1.5, (200, 200, 200), 2)

    # Leaderboard
    cv2.line(canvas, (p_x+20, 400), (p_x+380, 400), (100,100,100), 2)
    cv2.putText(canvas, "HALL OF FAME", (p_x+20, 440), cv2.FONT_HERSHEY_DUPLEX, 0.8, COLOR_ACCENT, 1)
    
    y = 480
    for idx, entry in enumerate(board[:6]):
        text = f"{idx+1}. {entry['name']}  -  {entry['score']}"
        cv2.putText(canvas, text, (p_x+20, y), cv2.FONT_HERSHEY_PLAIN, 1.3, COLOR_TEXT, 1)
        y += 35

    # Footer
    cv2.putText(canvas, "[N] New Player  [B] Bonus Round  [Q] Quit", (p_x+20, 680), cv2.FONT_HERSHEY_PLAIN, 1, (150,150,150), 1)

    return canvas

# --- MAIN LOOP ---
print("--- AI SYSTEM STARTED ---")
board_data = load_leaderboard()

while True:
    success, img = cap.read()
    if not success: break
    
    img = cv2.flip(img, 1)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)
    
    gesture = "UNKNOWN"
    
    if results.multi_hand_landmarks:
        for hand_lms in results.multi_hand_landmarks:
            mp_draw.draw_landmarks(img, hand_lms, mp_hands.HAND_CONNECTIONS,
                                   mp_draw.DrawingSpec(color=(0,255,0), thickness=2),
                                   mp_draw.DrawingSpec(color=(0,0,255), thickness=2))
            lm_list = []
            h, w, c = img.shape
            for id, lm in enumerate(hand_lms.landmark):
                lm_list.append([id, int(lm.x*w), int(lm.y*h)])
            gesture = get_gesture(lm_list)

    # Render Final UI
    final_frame = draw_ui(img, gesture, board_data)
    cv2.imshow("School Project", final_frame)
    
    key = cv2.waitKey(1)
    if key & 0xFF == ord('q'): break
    
    # --- NEW PLAYER LOGIC (N) ---
    if key & 0xFF == ord('n'):
        print("\n" + "="*40)
        name = input(">> ENTER STUDENT NAME: ").strip().upper()
        if name:
            game.player = name
            game.score = 0
            game.rounds = 0
            game.max_rounds = DEFAULT_ROUNDS
            game.active = True
            game.bonus_mode = False
            game.best_score = get_best_score(name)
            print(f"Welcome {name}! Best Score: {game.best_score}")
        print("="*40)

    # --- BONUS ADMIN LOGIC (B) ---
    if key & 0xFF == ord('b'):
        print("\n" + "*"*40)
        print("   ADMIN BONUS PANEL")
        print("*"*40)
        target_name = input(">> Who gets the Bonus? ").strip().upper()
        
        # Load user profile
        current_best = get_best_score(target_name)
        if current_best > 0 or target_name == game.player:
            game.player = target_name
            game.best_score = current_best
            
            # Unlock game state
            game.active = True
            game.rounds = 3 # Assume they finished normal rounds
            game.max_rounds = 4 # Add extra round
            game.score = current_best # Restore their score
            game.bonus_mode = True # Trigger visual effects
            
            print(f"BONUS GRANTED TO {target_name}!")
        else:
            print("Student not found in database.")
        print("*"*40)

    # --- PLAY ROUND LOGIC (SPACE) ---
    if (key & 0xFF == ord(' ') or key & 0xFF == ord('s')) and game.active:
        if game.rounds < game.max_rounds:
            
            # 1. Shuffle Animation
            for _ in range(10):
                temp_pc = random.choice(["ROCK", "PAPER", "SCISSORS"])
                # Draw simple overlay for shuffle
                shuffle_ui = final_frame.copy()
                cv2.putText(shuffle_ui, f"PC: {temp_pc}", (50, 600), cv2.FONT_HERSHEY_DUPLEX, 2, (255,255,255), 3)
                cv2.imshow("School Project", shuffle_ui)
                cv2.waitKey(50)

            # 2. Final Result
            pmove = gesture if gesture != "UNKNOWN" else "PAPER"
            cmove = random.choice(["ROCK", "PAPER", "SCISSORS"])
            
            res = "DRAW"
            color_res = (0, 255, 255)
            if (pmove=="ROCK" and cmove=="SCISSORS") or (pmove=="SCISSORS" and cmove=="PAPER") or (pmove=="PAPER" and cmove=="ROCK"):
                res = "WIN"
                game.score += 1
                color_res = COLOR_GREEN
            elif pmove != cmove:
                res = "LOSE"
                color_res = COLOR_RED

            # 3. Show Result Overlay
            overlay = final_frame.copy()
            cv2.rectangle(overlay, (300, 200), (980, 500), (0,0,0), cv2.FILLED)
            cv2.rectangle(overlay, (300, 200), (980, 500), color_res, 4)
            cv2.putText(overlay, res + "!", (550, 320), cv2.FONT_HERSHEY_DUPLEX, 2.5, color_res, 4)
            cv2.putText(overlay, f"PC: {cmove}", (530, 420), cv2.FONT_HERSHEY_PLAIN, 2, (255,255,255), 2)
            
            cv2.imshow("School Project", overlay)
            cv2.waitKey(2000)
            
            game.rounds += 1
            
            # 4. Check Game Over
            if game.rounds >= game.max_rounds:
                game.active = False
                game.bonus_mode = False # Reset bonus visual
                board_data = save_score(game.player, game.score)
                game.best_score = game.score # Update local best immediately

cap.release()
cv2.destroyAllWindows()
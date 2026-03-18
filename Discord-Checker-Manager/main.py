import customtkinter as ctk
import requests
import threading
import os
import time
import random
import urllib.parse
import json
import websocket  # pip install websocket-client

# --- GÖRÜNÜM AYARLARI ---
ctk.set_appearance_mode("Dark")


class FastChecker(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Dengo Discord Manager v4.7 - [Full Voice Control]")
        self.geometry("1200x850")

        self.token_data = []  # {token, label, checkbox, mute_btn, deaf_btn, is_muted, is_deaf}
        self.stop_raid_event = threading.Event()
        self.active_voice_sessions = {}  # token: {ws, guild_id, channel_id}

        # --- SOL PANEL ---
        self.sidebar = ctk.CTkFrame(self, width=300)
        self.sidebar.pack(side="left", fill="y", padx=10, pady=10)

        ctk.CTkLabel(self.sidebar, text="KONTROL PANELİ", font=("Arial", 18, "bold"), text_color="#3498db").pack(
            pady=20)

        self.btn_load = ctk.CTkButton(self.sidebar, text="Tokenleri Yükle (tokens.txt)", command=self.load_tokens)
        self.btn_load.pack(pady=5, padx=20)

        self.btn_recheck = ctk.CTkButton(self.sidebar, text="Seçilileri Kontrol Et", command=self.start_checking,
                                         fg_color="#27ae60", hover_color="#2ecc71")
        self.btn_recheck.pack(pady=5, padx=20)

        self.select_all_var = ctk.BooleanVar(value=True)
        self.btn_select_all = ctk.CTkCheckBox(self.sidebar, text="Tümünü Seç / Kaldır", variable=self.select_all_var,
                                              command=self.toggle_all_selection)
        self.btn_select_all.pack(pady=10, padx=20)

        # --- SES KANALI MODÜLÜ ---
        ctk.CTkLabel(self.sidebar, text="--- SES KANALI SIZMA ---", font=("Arial", 12, "bold"),
                     text_color="#2ecc71").pack(pady=(20, 5))
        self.voice_guild_id = ctk.CTkEntry(self.sidebar, placeholder_text="Sunucu (Guild) ID")
        self.voice_guild_id.pack(pady=2, padx=20)
        self.voice_channel_id = ctk.CTkEntry(self.sidebar, placeholder_text="Ses Kanal ID")
        self.voice_channel_id.pack(pady=2, padx=20)
        self.btn_voice_join = ctk.CTkButton(self.sidebar, text="SEÇİLİLERİ SESE SOK", fg_color="#27ae60",
                                            command=self.start_voice_threads)
        self.btn_voice_join.pack(pady=8, padx=20)
        self.btn_voice_leave = ctk.CTkButton(self.sidebar, text="SESİNDEN ÇIKAR", fg_color="#e74c3c",
                                             command=self.stop_voice_all)
        self.btn_voice_leave.pack(pady=2, padx=20)

        # --- REAKSİYON İŞLEMLERİ ---
        ctk.CTkLabel(self.sidebar, text="--- REAKSİYON İŞLEMLERİ ---", font=("Arial", 12, "bold"),
                     text_color="#f1c40f").pack(pady=(20, 5))
        self.react_channel_id = ctk.CTkEntry(self.sidebar, placeholder_text="Kanal ID")
        self.react_channel_id.pack(pady=2, padx=20)
        self.react_msg_id = ctk.CTkEntry(self.sidebar, placeholder_text="Mesaj ID")
        self.react_msg_id.pack(pady=2, padx=20)
        self.emoji_entry = ctk.CTkEntry(self.sidebar, placeholder_text="Emoji (Örn: 🔥)")
        self.emoji_entry.pack(pady=2, padx=20)
        self.btn_react = ctk.CTkButton(self.sidebar, text="SEÇİLİLERLE TEPKİ VER", fg_color="#9b59b6",
                                       command=self.start_reaction_threads)
        self.btn_react.pack(pady=8, padx=20)

        self.status = ctk.CTkLabel(self.sidebar, text="Sistem Hazır", text_color="gray")
        self.status.pack(side="bottom", pady=20)

        # --- SAĞ PANEL (Token Listesi) ---
        self.main_frame = ctk.CTkScrollableFrame(self, label_text="Token Ses ve Durum Yönetimi")
        self.main_frame.pack(side="right", fill="both", expand=True, padx=10, pady=10)

    def toggle_all_selection(self):
        state = self.select_all_var.get()
        for item in self.token_data:
            item["checkbox"].select() if state else item["checkbox"].deselect()

    def load_tokens(self):
        if not os.path.exists("tokens.txt"):
            self.status.configure(text="HATA: tokens.txt yok!", text_color="#e74c3c")
            return

        with open("tokens.txt", "r") as f:
            tokens = [line.strip() for line in f if line.strip()]

        for widget in self.main_frame.winfo_children(): widget.destroy()
        self.token_data = []

        for t in tokens:
            item_frame = ctk.CTkFrame(self.main_frame)
            item_frame.pack(fill="x", pady=2, padx=5)

            cb = ctk.CTkCheckBox(item_frame, text=f"...{t[-8:]}", width=100)
            cb.select()
            cb.pack(side="left", padx=5)

            lbl = ctk.CTkLabel(item_frame, text="Beklemede", width=120)
            lbl.pack(side="left", padx=5)

            # Ses Kontrol Butonları
            m_btn = ctk.CTkButton(item_frame, text="Mik: KAPALI", width=80, fg_color="#34495e",
                                  command=lambda tk=t: self.update_voice_state(tk, "mute"))
            m_btn.pack(side="right", padx=2)

            d_btn = ctk.CTkButton(item_frame, text="Sağır: HAYIR", width=80, fg_color="#34495e",
                                  command=lambda tk=t: self.update_voice_state(tk, "deaf"))
            d_btn.pack(side="right", padx=2)

            self.token_data.append({
                "token": t,
                "label": lbl,
                "checkbox": cb,
                "valid": False,
                "mute_btn": m_btn,
                "deaf_btn": d_btn,
                "is_muted": True,  # Başlangıçta mikrofon kapalı
                "is_deaf": False  # Başlangıçta kulaklık açık (gerçekçi)
            })
            threading.Thread(target=self.check_single_token, args=(self.token_data[-1],), daemon=True).start()

    def update_voice_state(self, token, action):
        """Butona basıldığında WebSocket üzerinden durumu günceller"""
        item = next((i for i in self.token_data if i["token"] == token), None)
        if not item or token not in self.active_voice_sessions:
            return

        session = self.active_voice_sessions[token]
        ws = session["ws"]

        if action == "mute":
            item["is_muted"] = not item["is_muted"]
            color = "#c0392b" if item["is_muted"] else "#27ae60"
            text = "Mik: KAPALI" if item["is_muted"] else "Mik: AÇIK"
            item["mute_btn"].configure(fg_color=color, text=text)

        elif action == "deaf":
            item["is_deaf"] = not item["is_deaf"]
            color = "#c0392b" if item["is_deaf"] else "#2ecc71"
            text = "Sağır: EVET" if item["is_deaf"] else "Sağır: HAYIR"
            item["deaf_btn"].configure(fg_color=color, text=text)

        # Discord'a yeni durumu gönder (Voice State Update Payload)
        try:
            ws.send(json.dumps({
                "op": 4,
                "d": {
                    "guild_id": session["guild_id"],
                    "channel_id": session["channel_id"],
                    "self_mute": item["is_muted"],
                    "self_deaf": item["is_deaf"]
                }
            }))
        except:
            pass

    def check_single_token(self, item):
        try:
            r = requests.get("https://discord.com/api/v9/users/@me", headers={'authorization': item["token"]},
                             timeout=5)
            if r.status_code == 200:
                user = r.json()['username']
                item["label"].configure(text=f"✅ {user}", text_color="#2ecc71")
                item["valid"] = True
            else:
                item["label"].configure(text="❌ GEÇERSİZ", text_color="#e74c3c")
                item["valid"] = False
        except:
            item["label"].configure(text="⚠️ HATA", text_color="yellow")

    def get_selected_tokens(self):
        return [item for item in self.token_data if item["checkbox"].get() and item["valid"]]

    def start_checking(self):
        for item in self.token_data:
            if item["checkbox"].get():
                item["label"].configure(text="...", text_color="gray")
                threading.Thread(target=self.check_single_token, args=(item,), daemon=True).start()

    # --- SES FONKSİYONLARI ---
    def start_voice_threads(self):
        guild, channel = self.voice_guild_id.get().strip(), self.voice_channel_id.get().strip()
        selected_items = self.get_selected_tokens()
        if not guild or not channel or not selected_items: return

        self.status.configure(text="Bağlanıyor...", text_color="#2ecc71")
        for item in selected_items:
            if item["token"] not in self.active_voice_sessions:
                threading.Thread(target=self.voice_ws_connect, args=(item, guild, channel), daemon=True).start()

    def stop_voice_all(self):
        tokens = list(self.active_voice_sessions.keys())
        for t in tokens:
            try:
                self.active_voice_sessions[t]["ws"].close()
                del self.active_voice_sessions[t]
                # Buton renklerini sıfırla
                it = next((i for i in self.token_data if i["token"] == t), None)
                if it:
                    it["mute_btn"].configure(fg_color="#34495e", text="Mik: KAPALI")
                    it["deaf_btn"].configure(fg_color="#34495e", text="Sağır: HAYIR")
            except:
                pass
        self.status.configure(text="Seslerden çıkıldı.", text_color="white")

    def voice_ws_connect(self, item, guild_id, channel_id):
        token = item["token"]
        ws = websocket.WebSocket()
        self.active_voice_sessions[token] = {"ws": ws, "guild_id": guild_id, "channel_id": channel_id}

        try:
            ws.connect("wss://gateway.discord.gg/?v=9&encoding=json")
            hello = json.loads(ws.recv())
            heartbeat_interval = hello['d']['heartbeat_interval'] / 1000

            ws.send(json.dumps({
                "op": 2,
                "d": {
                    "token": token,
                    "properties": {"$os": "windows", "$browser": "Chrome", "$device": ""},
                    "presence": {"status": "online", "afk": False},
                    "compress": False, "capabilities": 125
                }
            }))

            ready = ws.recv()

            # İLK GİRİŞ - Buton renklerini aktif hale getir
            item["mute_btn"].configure(fg_color="#c0392b")  # Kırmızı (Mute)
            item["deaf_btn"].configure(fg_color="#2ecc71")  # Yeşil (Kulaklık Açık)

            ws.send(json.dumps({
                "op": 4,
                "d": {
                    "guild_id": str(guild_id),
                    "channel_id": str(channel_id),
                    "self_mute": item["is_muted"],
                    "self_deaf": item["is_deaf"]
                }
            }))

            last_heartbeat = time.time()
            while token in self.active_voice_sessions:
                try:
                    ws.settimeout(0.5)
                    msg = ws.recv()
                except:
                    pass

                if time.time() - last_heartbeat > heartbeat_interval:
                    ws.send(json.dumps({"op": 1, "d": None}))
                    last_heartbeat = time.time()
                time.sleep(0.5)

        except:
            pass
        finally:
            if token in self.active_voice_sessions: del self.active_voice_sessions[token]
            try:
                ws.close()
            except:
                pass

    # --- REAKSİYON ---
    def start_reaction_threads(self):
        channel, msg, emoji = self.react_channel_id.get().strip(), self.react_msg_id.get().strip(), self.emoji_entry.get().strip()
        selected = self.get_selected_tokens()
        if not channel or not msg or not emoji or not selected: return
        enc_emoji = urllib.parse.quote(emoji)
        for it in selected:
            threading.Thread(target=lambda t=it["token"]: requests.put(
                f"https://discord.com/api/v9/channels/{channel}/messages/{msg}/reactions/{enc_emoji}/@me",
                headers={"Authorization": t}), daemon=True).start()


if __name__ == "__main__":
    FastChecker().mainloop()
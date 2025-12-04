import json
import os
import requests
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext

# --- Configuration ---
STORAGE = "fixbase.json"
SERVER = "http://192.168.78.195:5000"
REQ_TIMEOUT = 5


# --- Models ---
class Card:
    def __init__(self, title, description, steps, cli_commands, tags=None,
                 created_at=None, verified=False, history=None, id=None, local_saved=False):
        self.id = id
        self.title = title
        self.description = description
        self.steps = steps
        self.cli_commands = cli_commands
        self.tags = tags or []
        self.created_at = created_at or datetime.now().isoformat()
        self.verified = verified
        self.history = history or []
        self.local_saved = local_saved

    def to_dict(self):
        d = self.__dict__.copy()
        d.pop('local_saved', None)
        return d

    @staticmethod
    def from_dict(d):
        return Card(**d)


# --- Dialogs ---
class AuthDialog:
    def __init__(self, parent, title, confirm_text, show_confirm=False, on_close=None):
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.on_close = on_close

        tk.Label(self.top, text="Username").pack(anchor=tk.W)
        self.e_user = tk.Entry(self.top)
        self.e_user.pack(fill=tk.X)

        tk.Label(self.top, text="Password").pack(anchor=tk.W)
        self.e_pass = tk.Entry(self.top, show="*")
        self.e_pass.pack(fill=tk.X)

        self.e_pass2 = None
        if show_confirm:
            tk.Label(self.top, text="Confirm password").pack(anchor=tk.W)
            self.e_pass2 = tk.Entry(self.top, show="*")
            self.e_pass2.pack(fill=tk.X)

        btnf = tk.Frame(self.top)
        btnf.pack(pady=6)
        tk.Button(btnf, text=confirm_text, command=self.on_confirm).pack(side=tk.LEFT, padx=4)
        tk.Button(btnf, text="Cancel", command=self._on_cancel).pack(side=tk.LEFT)
        self.result = None

        self.top.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _on_cancel(self):
        self.result = None
        if callable(self.on_close):
            try:
                self.on_close()
            except Exception:
                pass
        self.top.destroy()

    def on_confirm(self):
        u, p = self.e_user.get().strip(), self.e_pass.get()
        if not u or not p:
            messagebox.showwarning("Error", "Username and password cannot be empty")
            return
        if self.e_pass2 and p != self.e_pass2.get():
            messagebox.showwarning("Error", "Passwords do not match")
            return
        self.result = (u, p)
        if callable(self.on_close):
            try:
                self.on_close()
            except Exception:
                pass
        self.top.destroy()


class CardDialog:
    def __init__(self, parent):
        self.top = tk.Toplevel(parent)
        self.top.title("Додати картку")

        self.e_title = self._add_field("Назва", 80)
        self.e_desc = self._add_area("Опис", 6)
        self.e_steps = self._add_area("Кроки вирішення", 6)
        self.e_cli = self._add_field("CLI-команди (через ;)", 80)
        self.e_tags = self._add_field("Теги (через ,)", 80)

        btn = tk.Frame(self.top)
        btn.pack(fill=tk.X, pady=4)
        tk.Button(btn, text="Додати", command=self.on_ok).pack(side=tk.LEFT, padx=4)
        tk.Button(btn, text="Відмінити", command=self.top.destroy).pack(side=tk.LEFT)
        self.result = None

    def _add_field(self, text, width):
        tk.Label(self.top, text=text).pack(anchor=tk.W)
        e = tk.Entry(self.top, width=width)
        e.pack(fill=tk.X)
        return e

    def _add_area(self, text, height):
        tk.Label(self.top, text=text).pack(anchor=tk.W)
        t = scrolledtext.ScrolledText(self.top, height=height)
        t.pack(fill=tk.BOTH)
        return t

    def on_ok(self):
        title = self.e_title.get().strip()
        if not title:
            messagebox.showwarning("Помилка", "Назва не може бути пуста")
            return
        desc = self.e_desc.get('1.0', tk.END).strip()
        steps = self.e_steps.get('1.0', tk.END).strip()
        cli = [s.strip() for s in self.e_cli.get().split(';') if s.strip()]
        tags = [t.strip() for t in self.e_tags.get().split(',') if t.strip()]
        self.result = (title, desc, steps, cli, tags)
        self.top.destroy()


# --- Windows ---
class DetailWindow:
    def __init__(self, parent, card: Card, app):
        self.card = card
        self.app = app
        top = self.top = tk.Toplevel(parent)
        top.title(card.title)
        top.geometry('700x500')

        tk.Label(top, text=card.title, font=(None, 16)).pack(anchor=tk.W)
        txt = scrolledtext.ScrolledText(top)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert(tk.END, self.format_card(card))
        txt.config(state='disabled')

        btns = tk.Frame(top)
        btns.pack(fill=tk.X)

        self.btn_copy_cli = tk.Button(btns, text="Копіювати всі CLI", command=self.copy_all_cli)
        self.btn_copy_cli.pack(side=tk.LEFT, padx=4)

        self.btn_mark_verified = tk.Button(btns, text="Позначити як перевірено (admin)", command=self.mark_verified)
        self.btn_mark_verified.pack(side=tk.LEFT)

        self.btn_toggle_local = tk.Button(btns, text="Зберегти локально / Вилучити (user)",
                                          command=self.toggle_local_save)
        self.btn_toggle_local.pack(side=tk.LEFT, padx=6)

        tk.Button(btns, text="Закрити", command=top.destroy).pack(side=tk.RIGHT, padx=4)

        role = app.role
        self.btn_mark_verified.config(state=tk.NORMAL if role == "admin" else tk.DISABLED)
        self.btn_toggle_local.config(state=tk.NORMAL if role in ("user", "admin") else tk.DISABLED)

    def format_card(self, c):
        return "\n".join([
            f"Опис:\n{c.description}\n",
            f"Кроки вирішення:\n{c.steps}\n",
            "CLI-команди:\n" + "\n".join(c.cli_commands) + "\n",
            "Теги: " + ", ".join(c.tags),
            f"Створено: {c.created_at}",
            f"Перевірено: {c.verified}",
            f"Локально збережено: {bool(getattr(c, 'local_saved', False))}"
        ])

    def copy_all_cli(self):
        self.top.clipboard_clear()
        self.top.clipboard_append("\n".join(self.card.cli_commands))
        messagebox.showinfo("Готово", "CLI-команди скопійовано в буфер обміну")

    def mark_verified(self):
        if self.card.verified:
            messagebox.showinfo("Інфо", "Картка вже перевірена")
            return
        if self.app.role != "admin":
            messagebox.showerror("Denied", "Тільки admin може позначати як перевірено")
            return

        try:
            r = requests.post(f"{SERVER}/cards/{self.card.id}/verify", headers=self.app.auth_headers(),
                              timeout=REQ_TIMEOUT)
            r.raise_for_status()
            updated = Card.from_dict(r.json())
            updated.local_saved = self.card.local_saved

            for i, c in enumerate(self.app.cards):
                if c.id == updated.id:
                    self.app.cards[i] = updated
                    break
            self.app.refresh_list()
            messagebox.showinfo("Готово", "Картку позначено як перевірено")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося відправити запит: {e}")

    def toggle_local_save(self):
        self.card.local_saved = not getattr(self.card, "local_saved", False)
        self.app.save_local()
        self.app.refresh_list()
        status = "збережено" if self.card.local_saved else "видалено з локальних"
        messagebox.showinfo("OK", f"Картку {status}.")


# --- Main Application ---
class FixbaseApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Fixbase")
        self.cards = []
        self.token = None
        self.role = "guest"
        self.username = None
        self.saved_local_cards = []
        self.auth_dialog = None
        self.build_gui()

        # Initial load
        if not self.load_from_server():
            self.load_local()
        self.merge_saved_into_master()
        self.update_buttons()
        self.refresh_list()

    def build_gui(self):
        left = tk.Frame(self.root)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=8)

        tk.Label(left, text="Пошук").pack(anchor=tk.W)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.refresh_list())
        tk.Entry(left, textvariable=self.search_var).pack(fill=tk.X)

        self.listbox = tk.Listbox(left, width=40)
        self.listbox.pack(fill=tk.Y, expand=True)
        self.listbox.bind('<Double-1>', lambda e: self.view_card())

        btn_frame = tk.Frame(left)
        btn_frame.pack(fill=tk.X)
        self.btn_add = tk.Button(btn_frame, text="Додати", command=self.add_card)
        self.btn_view = tk.Button(btn_frame, text="Переглянути", command=self.open_detail_window)
        self.btn_delete = tk.Button(btn_frame, text="Видалити", command=self.delete_card)
        for b in (self.btn_add, self.btn_view, self.btn_delete):
            b.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(left, text="Оновити (server)", command=self.on_refresh_click).pack(fill=tk.X, pady=4)

        self.auth_button = tk.Button(left, text="Login", command=self.login_flow)
        self.auth_button.pack(fill=tk.X)
        self.register_button = tk.Button(left, text="Register", command=self.register_flow)
        self.register_button.pack(fill=tk.X, pady=(2, 0))

        self.lbl_user = tk.Label(left, text="guest", fg="gray")
        self.lbl_user.pack(anchor=tk.W, pady=(6, 0))

        right = tk.Frame(self.root)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.detail_title = tk.Label(right, text="Оберіть картку для перегляду", font=(None, 14))
        self.detail_title.pack(anchor=tk.W)
        self.detail_text = scrolledtext.ScrolledText(right, state='disabled')
        self.detail_text.pack(fill=tk.BOTH, expand=True)

    def auth_headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def on_refresh_click(self):
        if self.load_from_server():
            self.merge_saved_into_master()
            self.refresh_list()
            messagebox.showinfo("Готово", "Список карток оновлено з сервера!")

    # --- Auth Flow ---
    def login_flow(self):
        if self.auth_dialog and getattr(self.auth_dialog, "top", None) and self.auth_dialog.top.winfo_exists():
            messagebox.showinfo("Інфо", "Вікно логіну вже відкрито")
            return

        dlg = AuthDialog(self.root, "Login", "Login", on_close=self._on_auth_dialog_close)
        self.auth_dialog = dlg
        self.root.wait_window(dlg.top)
        if not dlg.result:
            return

        username, password = dlg.result
        try:
            r = requests.post(f"{SERVER}/login", json={"username": username, "password": password}, timeout=REQ_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            self.token, self.role, self.username = data.get("token"), data.get("role", "guest"), data.get("username", username)
            self._on_auth_success()
            messagebox.showinfo("OK", f"Logged in as {self.username} ({self.role})")
        except Exception as e:
            messagebox.showerror("Login failed", str(e))

    def register_flow(self):
        dlg = AuthDialog(self.root, "Register", "Register", show_confirm=True)
        self.root.wait_window(dlg.top)
        if not dlg.result: return

        username, password = dlg.result
        try:
            r = requests.post(f"{SERVER}/register", json={"username": username, "password": password},
                              timeout=REQ_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            self.token, self.role, self.username = data.get("token"), data.get("role", "user"), username
            self._on_auth_success()
            messagebox.showinfo("OK", "Registered and logged in")
        except Exception as e:
            messagebox.showerror("Register failed", str(e))

    def _on_auth_success(self):
        self.lbl_user.config(text=f"{self.username} ({self.role})", fg="green")
        self.auth_button.config(text="Logout", command=self.logout_flow)
        self.register_button.config(state=tk.DISABLED)
        self.load_from_server()
        self.merge_saved_into_master()
        self.update_buttons()
        self.refresh_list()

    def logout_flow(self):
        self.token, self.role, self.username = None, "guest", None
        self.lbl_user.config(text="guest", fg="gray")
        self.auth_button.config(text="Login", command=self.login_flow)
        self.register_button.config(state=tk.NORMAL)
        self.cards = []
        self.load_local()
        self.merge_saved_into_master()
        self.update_buttons()
        self.refresh_list()
        messagebox.showinfo("OK", "Logged out")

    def update_buttons(self):
        state = tk.NORMAL if self.role == "admin" else tk.DISABLED
        self.btn_add.config(state=state)
        self.btn_delete.config(state=state)
        self.btn_view.config(state=tk.NORMAL)

    # --- Storage & Sync ---
    def load_local_saved_cards(self):
        if os.path.exists(STORAGE):
            try:
                with open(STORAGE, 'r', encoding='utf-8') as f:
                    cards = [Card.from_dict(d) for d in json.load(f)]
                    for c in cards: c.local_saved = True
                    return cards
            except Exception:
                return []
        return []

    def save_local(self):
        try:
            with open(STORAGE, 'w', encoding='utf-8') as f:
                json.dump([c.to_dict() for c in self.cards if getattr(c, 'local_saved', False)],
                          f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showwarning("Помилка", f"Не вдалося зберегти локальну копію: {e}")

    def load_local(self):
        if os.path.exists(STORAGE):
            try:
                with open(STORAGE, 'r', encoding='utf-8') as f:
                    self.cards = [Card.from_dict(d) for d in json.load(f)]
                    for c in self.cards: c.local_saved = True
            except Exception:
                self.cards = []
        else:
            self.cards = []

    def load_from_server(self):
        try:
            r = requests.get(f"{SERVER}/cards", headers=self.auth_headers(), timeout=REQ_TIMEOUT)
            r.raise_for_status()
            self.cards = [Card.from_dict(d) for d in r.json()]
            return True
        except Exception as e:
            messagebox.showwarning("Помилка зв'язку",
                                   f"Не вдалося завантажити дані з сервера: {e}\nЗавантажую локально")
            return False

    def merge_saved_into_master(self):
        self.saved_local_cards = self.load_local_saved_cards()
        saved_by_id = {c.id: c for c in self.saved_local_cards if c.id}
        ids_on_master = {c.id for c in self.cards if c.id}

        for c in self.cards:
            if c.id in saved_by_id: c.local_saved = True

        for s in self.saved_local_cards:
            if not s.id or s.id not in ids_on_master:
                s.local_saved = True
                self.cards.append(s)

    # --- Listbox Logic ---
    def refresh_list(self):
        q = self.search_var.get().lower()
        self.listbox.delete(0, tk.END)
        for i, c in enumerate(self.cards):
            match = not q or q in (c.title or "").lower() or q in (c.description or "").lower() or any(
                q in t.lower() for t in c.tags)
            if match:
                mark = '✔' if c.verified else ' '
                loc = '*' if getattr(c, 'local_saved', False) else ' '
                self.listbox.insert(tk.END, f"{i + 1}. [{mark}{loc}] {c.title}")

    def selected_index(self):
        sel = self.listbox.curselection()
        if not sel: return None
        try:
            idx = int(self.listbox.get(sel[0]).split('.', 1)[0]) - 1
            return idx if 0 <= idx < len(self.cards) else None
        except:
            return None

    # --- CRUD Actions ---
    def add_card(self):
        if self.role != "admin":
            messagebox.showerror("Denied", "Тільки admin може додавати картки")
            return
        dlg = CardDialog(self.root)
        self.root.wait_window(dlg.top)
        if not dlg.result: return

        title, desc, steps, cli, tags = dlg.result
        card = Card(title, desc, steps, cli, tags)
        try:
            r = requests.post(f"{SERVER}/cards", json=card.to_dict(), headers=self.auth_headers(), timeout=REQ_TIMEOUT)
            r.raise_for_status()
            self.cards.append(Card.from_dict(r.json()))
            self.refresh_list()
            messagebox.showinfo("OK", "Картка створена на сервері")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося створити картку: {e}")

    def delete_card(self):
        idx = self.selected_index()
        if idx is None:
            messagebox.showinfo("Інфо", "Оберіть картку для видалення.")
            return

        if self.role != "admin":
            messagebox.showerror("Denied", "Тільки admin може видаляти картки")
            return

        if not messagebox.askyesno("Підтвердження", "Видалити вибрану картку?"):
            return

        card = self.cards[idx]
        try:
            if card.id:
                r = requests.delete(f"{SERVER}/cards/{card.id}", headers=self.auth_headers(), timeout=REQ_TIMEOUT)
                r.raise_for_status()
            del self.cards[idx]
            self.save_local()
            self.refresh_list()
            messagebox.showinfo("OK", "Картку видалено")
        except Exception as e:
            messagebox.showerror("Помилка", f"Не вдалося видалити картку: {e}")

    def open_detail_window(self):
        idx = self.selected_index()
        if idx is None:
            messagebox.showinfo("Інфо", "Оберіть картку у списку.")
            return
        DetailWindow(self.root, self.cards[idx], self)

    def view_card(self):
        self.open_detail_window()

    def _on_auth_dialog_close(self):
        self.auth_dialog = None


if __name__ == '__main__':
    root = tk.Tk()
    app = FixbaseApp(root)
    root.mainloop()

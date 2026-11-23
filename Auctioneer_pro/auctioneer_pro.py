import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from PIL import Image, ImageTk
import json
from PIL import Image, ImageTk, ImageFilter, ImageOps, ImageEnhance
try:
    from screeninfo import get_monitors
except ImportError:
    get_monitors = None


APP_TITLE = "AUCTIONEER PRO"
STATE_FILE = Path.home() / ".auctioneer_pro_state.json"

# AUCTIONEER PRO PALETTE
BLUE = "#2391FF"
YELLOW = "#FFF83F"
AMBER = "#FFCD54"
PINK = "#F70063"

# Light surfaces keep the vivid palette clear and readable.
BG = "#EAF0FA"
PANEL = "#F1F5FC"
INPUT = "#FAFCFF"
ACCENT = BLUE
ACCENT_HOVER = "#1479DB"
TEXT = "#20242A"
MUTED = "#68717D"
BORDER = "#D4DEED"
SELECT = "#DCEEFF"


class CricketAuction:

    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1250x780")
        self.root.minsize(1000, 650)
        self.root.configure(bg=BG)

        self.directory = None
        self.max_players = 0
        self.auction_name = ""

        # opened = every player called at least once.
        # pending = called players whose result has not been decided yet.
        self.opened = set()
        self.pending = set()
        self.sold = set()
        self.unsold = set()
        self.indecisive = set()
        self.available_cards = {}

        # Drag-and-drop state for player-card tiles.
        self.dragged_player = None
        self.drag_source = None
        self.drag_ghost = None
        self.list_frames = {}
        self.list_contents = {}
        self.list_canvases = {}
        self.active_list_canvas = None

        # Wallpaper is stored beside this Python file.
        self.background_path = Path(__file__).with_name("auctioneer_background.jpg")
        self.background_photo = None
        self.background_label = None
        self._background_original = None
        self._background_resize_after_id = None
        self._background_configure_bound = False

        self.viewer = None
        self.viewer_image = None
        self.preview_image = None
        self.close_viewer_button = None
        self.sold_button = None
        self.unsold_button = None
        self.current_player_number = None
        self.overlay_widget = None
        self.overlay_after_id = None

        self.state = self.load_state_file()

        self.setup_theme()
        self.root.bind_all("<B1-Motion>", self.drag_card_motion, add="+")
        self.root.bind_all("<ButtonRelease-1>", self.finish_card_drag, add="+")
        self.root.bind_all("<MouseWheel>", self.scroll_active_list, add="+")
        self.root.bind_all("<Button-4>", self.scroll_active_list, add="+")
        self.root.bind_all("<Button-5>", self.scroll_active_list, add="+")
        self.show_setup()

    # ================================================
    # THEME
    # ================================================

    def setup_theme(self):
        style = ttk.Style()

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            ".",
            background=BG,
            foreground=TEXT,
            font=("Arial", 10)
        )

        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)

        style.configure(
            "TLabel",
            background=BG,
            foreground=TEXT
        )

        style.configure(
            "Muted.TLabel",
            background=BG,
            foreground=MUTED
        )

        style.configure(
            "Title.TLabel",
            background=BG,
            foreground=ACCENT,
            font=("Arial", 24, "bold")
        )

        style.configure(
            "Heading.TLabel",
            background=BG,
            foreground=TEXT,
            font=("Arial", 13, "bold")
        )

        style.configure(
            "TButton",
            background=PANEL,
            foreground=TEXT,
            bordercolor=BORDER,
            padding=(12, 8),
            font=("Arial", 10, "bold")
        )

        style.map(
            "TButton",
            background=[
                ("active", ACCENT_HOVER),
                ("pressed", ACCENT)
            ]
        )

        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#ffffff",
            bordercolor=ACCENT,
            padding=(14, 10),
            font=("Arial", 10, "bold")
        )

        style.map(
            "Accent.TButton",
            background=[
                ("active", ACCENT_HOVER),
                ("pressed", ACCENT_HOVER)
            ]
        )

        style.configure(
            "Danger.TButton",
            background="#a93232",
            foreground="#ffffff",
            bordercolor="#a93232"
        )

        style.map(
            "Danger.TButton",
            background=[
                ("active", "#c0392b"),
                ("pressed", "#922b21")
            ]
        )

        style.configure(
            "TLabelframe",
            background=PANEL,
            foreground=ACCENT,
            bordercolor=BORDER
        )

        style.configure(
            "TLabelframe.Label",
            background=PANEL,
            foreground=ACCENT,
            font=("Arial", 11, "bold")
        )

        style.configure(
            "TEntry",
            fieldbackground=INPUT,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=BORDER,
            padding=8
        )

    # ================================================
    # SAVE AND LOAD
    # ================================================

    def load_state_file(self):
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r") as file:
                    return json.load(file)
            except (json.JSONDecodeError, OSError):
                pass

        return {}

    def save_state_file(self):
        try:
            with open(STATE_FILE, "w") as file:
                json.dump(self.state, file, indent=4)
        except OSError as error:
            messagebox.showerror(
                "Save Error",
                f"Could not save auction progress:\n{error}"
            )

    def session_key(self):
        return str(self.directory.resolve())

    def restore_session(self):
        session = self.state.get(self.session_key(), {})

        self.opened = set(session.get("opened", []))
        self.sold = set(session.get("sold", []))
        self.unsold = set(session.get("unsold", []))
        self.indecisive = set(session.get("indecisive", []))

        # Older JSON files only stored "opened". Treat those players as
        # unresolved so their progress is not lost during the upgrade.
        if "pending" in session:
            self.pending = set(session.get("pending", []))
        else:
            decided = self.sold | self.unsold | self.indecisive
            self.pending = self.opened - decided

        if not self.auction_name:
            self.auction_name = session.get("auction_name", "My Auction")

    def save_session(self):
        if self.directory is None:
            return

        self.state[self.session_key()] = {
            "opened": sorted(self.opened),
            "pending": sorted(self.pending),
            "sold": sorted(self.sold),
            "unsold": sorted(self.unsold),
            "indecisive": sorted(self.indecisive),
            "max_players": self.max_players,
            "auction_name": self.auction_name
        }
        self.save_state_file()

    # ================================================
    # WALLPAPER BACKGROUND
    # ================================================

    def show_page_background(self):
        """Display a softly blurred, darkened wallpaper behind each main page."""
        if not self.background_path.exists():
            self.root.configure(bg=BG)
            print(f"Background not found: {self.background_path}")
            return

        try:
            original = Image.open(self.background_path).convert("RGB")
            # Blur the wallpaper itself; foreground widgets and text stay sharp.
            self._background_original = original.filter(ImageFilter.GaussianBlur(0))
            self.background_label = tk.Label(
                self.root, bd=0, highlightthickness=0, bg=BG
            )
            self.background_label.place(x=0, y=0, relwidth=1, relheight=1)
            self.background_label.lower()
            if not self._background_configure_bound:
                self.root.bind("<Configure>", self.schedule_background_resize, add="+")
                self._background_configure_bound = True
            self.resize_page_background()
        except Exception as exc:
            print(f"Could not load background image: {exc}")
            self.root.configure(bg=BG)

    def schedule_background_resize(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        if self._background_resize_after_id is not None:
            try:
                self.root.after_cancel(self._background_resize_after_id)
            except tk.TclError:
                pass
        self._background_resize_after_id = self.root.after(
            120, self.resize_page_background
        )

    def resize_page_background(self):
        self._background_resize_after_id = None
        if self.background_label is None or not self.background_label.winfo_exists():
            return
        width = max(1, self.root.winfo_width())
        height = max(1, self.root.winfo_height())
        try:
            image = ImageOps.fit(
                self._background_original,
                (width, height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5)
            )
            # Dim slightly so the light frosted-style panels remain readable.
            image = ImageEnhance.Brightness(image).enhance(0.70)
            self.background_photo = ImageTk.PhotoImage(image)
            self.background_label.configure(image=self.background_photo)
            self.background_label.lower()
        except Exception as exc:
            print(f"Could not resize background image: {exc}")

    # ================================================
    # SETUP SCREEN
    # ================================================

    def show_setup(self):
        self.clear_window()
        self.show_page_background()
        self.preview_image = None
        self.close_viewer_button = None

        container = ttk.Frame(self.root, padding=35)
        container.pack(expand=True)

        ttk.Label(
            container,
            text="AUCTIONEER PRO",
            style="Title.TLabel"
        ).pack(pady=(0, 8))

        ttk.Label(
            container,
            text="The future of passive auctions",
            style="Muted.TLabel"
        ).pack(pady=(0, 35))

        ttk.Label(
            container,
            text="AUCTION NAME",
            style="Heading.TLabel"
        ).pack(anchor="w", pady=(10, 5))

        self.name_entry = ttk.Entry(
            container,
            width=48,
            font=("Arial", 12)
        )
        self.name_entry.pack(fill="x", pady=5)

        ttk.Label(
            container,
            text="PLAYER CARD DIRECTORY",
            style="Heading.TLabel"
        ).pack(anchor="w", pady=(20, 5))

        folder_frame = ttk.Frame(container)
        folder_frame.pack(fill="x", pady=5)

        self.folder_var = tk.StringVar()

        ttk.Entry(
            folder_frame,
            textvariable=self.folder_var,
            width=40
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            folder_frame,
            text="BROWSE",
            command=self.choose_directory
        ).pack(side="left", padx=8)

        ttk.Label(
            container,
            text="MAXIMUM PLAYER NUMBER",
            style="Heading.TLabel"
        ).pack(anchor="w", pady=(20, 5))

        self.max_entry = ttk.Entry(container, width=15)
        self.max_entry.pack(anchor="w", pady=5)

        ttk.Label(
            container,
            text="Example: Enter 100 if your cards are numbered 1–100.",
            style="Muted.TLabel"
        ).pack(anchor="w")

        ttk.Button(
            container,
            text="START AUCTION",
            style="Accent.TButton",
            command=self.start_auction
        ).pack(fill="x", pady=35, ipady=5)

    def choose_directory(self):
        folder = filedialog.askdirectory(
            title="Select Player Card Directory"
        )

        if not folder:
            return

        self.folder_var.set(folder)

        key = str(Path(folder).resolve())
        session = self.state.get(key, {})

        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(
            0,
            session.get("auction_name", "")
        )

        self.max_entry.delete(0, tk.END)

        if session.get("max_players"):
            self.max_entry.insert(
                0,
                str(session["max_players"])
            )

    def start_auction(self):
        folder = self.folder_var.get().strip()

        if not folder or not Path(folder).is_dir():
            messagebox.showerror(
                "Invalid Directory",
                "Please select a valid card directory."
            )
            return

        name = self.name_entry.get().strip()

        if not name:
            messagebox.showerror(
                "Missing Auction Name",
                "Please enter an auction name."
            )
            return

        try:
            maximum = int(self.max_entry.get())

            if maximum < 1:
                raise ValueError

        except ValueError:
            messagebox.showerror(
                "Invalid Number",
                "Enter a valid maximum player number."
            )
            return

        self.directory = Path(folder)
        self.max_players = maximum
        self.auction_name = name

        self.restore_session()
        self.scan_files()
        self.show_dashboard()

    # ================================================
    # FILE SCANNING
    # ================================================

    def scan_files(self):
        self.available_cards = {}

        if not self.directory:
            return

        for file in self.directory.iterdir():

            if not file.is_file():
                continue

            if file.suffix.lower() not in (".jpg", ".jpeg"):
                continue

            filename = file.stem.strip()

            if not filename.isdigit():
                continue

            number = int(filename)

            if 1 <= number <= self.max_players:
                self.available_cards[number] = file

    # ================================================
    # DASHBOARD
    # ================================================

    def show_dashboard(self):
        self.clear_window()
        ##self.show_page_background()

        self.root.grid_rowconfigure(5, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(self.root, padding=15)
        header.grid(row=0, column=0, sticky="ew")

        title_frame = ttk.Frame(header)
        title_frame.pack(side="left")
        ttk.Label(title_frame, text=self.auction_name, style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_frame, text="AUCTION CONTROL PANEL", style="Muted.TLabel").pack(anchor="w")
        ttk.Button(header, text="END AUCTION", style="Danger.TButton", command=self.end_auction).pack(side="right")

        ttk.Label(self.root, text=f"CARD DIRECTORY: {self.directory}", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", padx=20
        )
        ttk.Separator(self.root).grid(row=2, column=0, sticky="ew", pady=8)

        input_frame = ttk.Frame(self.root, padding=12)
        input_frame.grid(row=3, column=0, sticky="ew")
        ttk.Label(input_frame, text="PLAYER NUMBER:", style="Heading.TLabel").pack(side="left")

        self.player_entry = ttk.Entry(input_frame, font=("Arial", 16), width=12)
        self.player_entry.pack(side="left", padx=12)
        self.player_entry.bind("<Return>", self.open_player)

        ttk.Button(input_frame, text="DISPLAY CARD", style="Accent.TButton", command=self.open_player).pack(side="left", padx=4)
        self.close_viewer_button = ttk.Button(
            input_frame, text="CLOSE FULLSCREEN VIEWER", command=self.close_viewer, state="disabled"
        )
        self.close_viewer_button.pack(side="left", padx=8)

        self.sold_button = ttk.Button(
            input_frame, text="SOLD", command=lambda: self.record_result("SOLD"), state="disabled"
        )
        self.sold_button.pack(side="left", padx=(8, 3))
        self.unsold_button = ttk.Button(
            input_frame, text="UNSOLD", command=lambda: self.record_result("UNSOLD"), state="disabled"
        )
        self.unsold_button.pack(side="left", padx=3)
        ttk.Button(input_frame, text="REFRESH", command=self.refresh_files).pack(side="right")

        self.stats_label = ttk.Label(self.root, font=("Arial", 12, "bold"))
        self.stats_label.grid(row=4, column=0, pady=6)

        # Five status lists plus the card preview, arranged in a 3 x 2 grid.
        content = ttk.Frame(self.root, padding=8)
        content.grid(row=5, column=0, sticky="nsew")
        for col in range(3):
            content.columnconfigure(col, weight=1, uniform="auction_columns")
        for row in range(2):
            content.rowconfigure(row, weight=1, uniform="auction_rows")

        list_specs = [
            ("UNOPENED PLAYERS", "unopened", 0, 0),
            ("OPENED PLAYERS", "opened", 0, 1),
            ("SOLD PLAYERS", "sold", 0, 2),
            ("UNSOLD PLAYERS", "unsold", 1, 0),
            ("INDECISIVE PLAYERS", "indecisive", 1, 1),
        ]
        for title, key, row, col in list_specs:
            frame = ttk.LabelFrame(content, text=title, padding=6)
            frame.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
            drop_area = tk.Frame(
                frame, bg=PANEL, bd=0, highlightthickness=1,
                highlightbackground=BORDER
            )
            drop_area.pack(fill="both", expand=True)

            # Scrollable viewport: player tiles live inside the canvas window.
            canvas = tk.Canvas(
                drop_area, bg=PANEL, bd=0, highlightthickness=0,
                yscrollincrement=35
            )
            scrollbar = ttk.Scrollbar(
                drop_area, orient="vertical", command=canvas.yview
            )
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)

            tile_container = tk.Frame(canvas, bg=PANEL)
            window_id = canvas.create_window(
                (0, 0), window=tile_container, anchor="nw"
            )

            def update_scroll_region(event, c=canvas):
                c.configure(scrollregion=c.bbox("all"))

            def fit_tile_width(event, c=canvas, item=window_id):
                c.itemconfigure(item, width=event.width)

            tile_container.bind("<Configure>", update_scroll_region)
            canvas.bind("<Configure>", fit_tile_width)
            canvas.bind("<Enter>", lambda event, c=canvas: self.set_active_list_canvas(c))
            canvas.bind("<Leave>", lambda event: self.clear_active_list_canvas())

            setattr(self, f"{key}_list", drop_area)
            self.list_frames[key] = drop_area
            self.list_contents[key] = tile_container
            self.list_canvases[key] = canvas

        preview_frame = ttk.LabelFrame(content, text="PLAYER CARD PREVIEW", padding=8)
        preview_frame.grid(row=1, column=2, sticky="nsew", padx=4, pady=4)
        self.preview_title = ttk.Label(preview_frame, text="Select a player", style="Heading.TLabel")
        self.preview_title.pack(pady=6)
        self.preview_label = tk.Label(
            preview_frame, text="No player selected", bg=PANEL, fg=MUTED, font=("Arial", 12)
        )
        self.preview_label.pack(fill="both", expand=True)
        ttk.Label(
            preview_frame, text="Double-click a player to open the full card.", style="Muted.TLabel"
        ).pack(pady=6)

        self.update_lists()
        self.player_entry.focus_set()

    def set_active_list_canvas(self, canvas):
        self.active_list_canvas = canvas

    def clear_active_list_canvas(self):
        self.active_list_canvas = None

    def scroll_active_list(self, event):
        canvas = self.active_list_canvas
        if canvas is None or not canvas.winfo_exists():
            return

        # Linux uses Button-4 / Button-5; other platforms use MouseWheel.
        if getattr(event, "num", None) == 4:
            direction = -1
        elif getattr(event, "num", None) == 5:
            direction = 1
        else:
            direction = -1 if event.delta > 0 else 1

        canvas.yview_scroll(direction * 3, "units")
        return "break"

    def set_drop_highlight(self, key, active):
        frame = self.list_frames.get(key)
        if frame is not None and frame.winfo_exists():
            frame.configure(
                highlightbackground=ACCENT if active else BORDER,
                highlightthickness=3 if active else 1
            )

    def begin_card_drag(self, event, number, source):
        self.dragged_player = number
        self.drag_source = source
        self.preview_number(number)

        # Create a floating copy of the tile that follows the pointer.
        self.drag_ghost = tk.Toplevel(self.root)
        self.drag_ghost.overrideredirect(True)
        self.drag_ghost.attributes("-topmost", True)
        ghost = tk.Frame(
            self.drag_ghost, bg="#FFFFFF",
            highlightthickness=2, highlightbackground=ACCENT,
            padx=16, pady=10
        )
        ghost.pack()
        tk.Label(
            ghost, text=f"PLAYER  {number}", bg="#FFFFFF", fg=TEXT,
            font=("Arial", 12, "bold")
        ).pack()
        tk.Label(
            ghost, text="DROP INTO A LIST", bg="#FFFFFF", fg=ACCENT,
            font=("Arial", 8, "bold")
        ).pack(pady=(3, 0))
        self.move_drag_ghost(event.x_root, event.y_root)
        self.root.configure(cursor="fleur")

    def move_drag_ghost(self, x_root, y_root):
        if self.drag_ghost is not None and self.drag_ghost.winfo_exists():
            self.drag_ghost.geometry(f"+{x_root + 16}+{y_root + 14}")

    def drag_card_motion(self, event=None):
        if self.dragged_player is None or event is None:
            return

        self.move_drag_ghost(event.x_root, event.y_root)
        target = self.find_drop_list_at(event.x_root, event.y_root)
        for key in self.list_frames:
            self.set_drop_highlight(key, key == target)

    def find_drop_list_at(self, x_root, y_root):
        # Use the actual list-frame bounds rather than winfo_containing(),
        # because the floating drag preview sits above the dashboard.
        for key, frame in self.list_frames.items():
            if not frame.winfo_exists():
                continue
            left = frame.winfo_rootx()
            top = frame.winfo_rooty()
            right = left + frame.winfo_width()
            bottom = top + frame.winfo_height()
            if left <= x_root <= right and top <= y_root <= bottom:
                return key
        return None

    def finish_card_drag(self, event):
        if self.dragged_player is None:
            return

        number = self.dragged_player
        target = self.find_drop_list_at(event.x_root, event.y_root)

        self.dragged_player = None
        self.drag_source = None
        self.root.configure(cursor="")

        if self.drag_ghost is not None:
            try:
                self.drag_ghost.destroy()
            except tk.TclError:
                pass
            self.drag_ghost = None

        for key in self.list_frames:
            self.set_drop_highlight(key, False)

        if target is not None:
            self.move_player_to_list(number, target)

    def move_player_to_list(self, number, target):
        if number not in self.available_cards:
            return

        self.opened.discard(number)
        self.pending.discard(number)
        self.sold.discard(number)
        self.unsold.discard(number)
        self.indecisive.discard(number)

        if target == "unopened":
            pass
        elif target == "opened":
            self.opened.add(number)
            self.pending.add(number)
        elif target == "sold":
            self.opened.add(number)
            self.sold.add(number)
        elif target == "unsold":
            self.opened.add(number)
            self.unsold.add(number)
        elif target == "indecisive":
            self.opened.add(number)
            self.indecisive.add(number)

        self.update_lists()

        if number == self.current_player_number:
            if target == "sold":
                self.show_result_overlay("SOLD")
            elif target == "unsold":
                self.show_result_overlay("UNSOLD")

    def bind_card_events(self, widget, number, source):
        widget.bind(
            "<ButtonPress-1>",
            lambda event, n=number, k=source: self.begin_card_drag(event, n, k)
        )
        widget.bind(
            "<Double-Button-1>",
            lambda event, n=number: self.open_player_from_card(n)
        )
        for child in widget.winfo_children():
            self.bind_card_events(child, number, source)

    def open_player_from_card(self, number):
        self.player_entry.delete(0, tk.END)
        self.player_entry.insert(0, str(number))
        self.open_player()

    # LIST MANAGEMENT
    # ================================================

    def update_lists(self):
        groups = {
            "unopened": set(self.available_cards) - self.opened,
            "opened": self.pending,
            "sold": self.sold,
            "unsold": self.unsold,
            "indecisive": self.indecisive,
        }
        accents = {
            "unopened": BLUE,
            "opened": BLUE,
            "sold": PINK,
            "unsold": AMBER,
            "indecisive": "#A87900",
        }

        existing = set(self.available_cards)
        for key, numbers in groups.items():
            frame = self.list_contents.get(key)
            if frame is None:
                continue
            for child in frame.winfo_children():
                child.destroy()

            for number in sorted(numbers & existing):
                tile = tk.Frame(
                    frame, bg=INPUT, highlightthickness=1,
                    highlightbackground=BORDER, padx=10, pady=9,
                    cursor="hand2"
                )
                tile.pack(fill="x", padx=6, pady=4)
                stripe = tk.Frame(tile, bg=accents[key], width=5)
                stripe.pack(side="left", fill="y", padx=(0, 10))
                tk.Label(
                    tile, text=f"PLAYER  {number}", bg=INPUT, fg=TEXT,
                    font=("Arial", 12, "bold"), anchor="w"
                ).pack(side="left", fill="x", expand=True)
                tk.Label(
                    tile, text="⠿  DRAG", bg=INPUT, fg=accents[key],
                    font=("Arial", 8, "bold")
                ).pack(side="right")
                self.bind_card_events(tile, number, key)

        called = len(self.opened & existing)
        unopened = len(existing - self.opened)
        self.stats_label.config(
            text=(
                f"CALLED: {called}   |   UNOPENED: {unopened}   |   "
                f"SOLD: {len(self.sold & existing)}   |   "
                f"UNSOLD: {len(self.unsold & existing)}   |   "
                f"INDECISIVE: {len(self.indecisive & existing)}"
            )
        )
        self.save_session()
        self.clear_preview()

    def move_to_opened(self):
        for index in self.unopened_list.curselection():
            number = int(self.unopened_list.get(index))
            self.opened.add(number)
            self.pending.add(number)
        self.update_lists()

    def move_to_unopened(self):
        for index in self.opened_list.curselection():
            number = int(self.opened_list.get(index))
            self.opened.discard(number)
            self.pending.discard(number)
        self.update_lists()

    def refresh_files(self):
        self.scan_files()
        self.update_lists()

        messagebox.showinfo(
            "Refresh Complete",
            "Player cards have been rescanned."
        )

    # ================================================
    # MINI PREVIEW
    # ================================================

    def clear_preview(self):
        self.preview_title.config(text="Select a player")

        self.preview_label.config(
            image="",
            text="No player selected"
        )

        self.preview_image = None

    def preview_selected(self, event=None):
        return

    def preview_number(self, number):
        if number not in self.available_cards:
            return
        image_path = self.available_cards[number]
        try:
            image = Image.open(image_path).convert("RGB")
            image.thumbnail((420, 520), Image.Resampling.LANCZOS)
            self.preview_image = ImageTk.PhotoImage(image)
            self.preview_title.config(
                text=f"PLAYER {number} — {self.get_player_status(number).upper()}"
            )
            self.preview_label.config(image=self.preview_image, text="")
        except Exception as error:
            self.clear_preview()
            self.preview_label.config(text=f"Could not load image:\n{error}")

    def get_player_status(self, number):
        if number in self.sold:
            return "sold"
        if number in self.unsold:
            return "unsold"
        if number in self.indecisive:
            return "indecisive"
        if number in self.pending:
            return "opened"
        return "unopened"

    def open_selected_from_list(self, event=None):
        selected_list = event.widget
        selection = selected_list.curselection()

        if selection:
            number = int(
                selected_list.get(selection[0])
            )

            self.player_entry.delete(0, tk.END)
            self.player_entry.insert(0, str(number))

            self.open_player()

    # ================================================
    # FULLSCREEN VIEWER
    # ================================================

    def open_player(self, event=None):
        try:
            number = int(self.player_entry.get())
        except ValueError:
            messagebox.showerror("Invalid Player", "Enter a valid player number.")
            return

        if number < 1 or number > self.max_players:
            messagebox.showerror(
                "Invalid Player", f"Player number must be between 1 and {self.max_players}."
            )
            return
        if number not in self.available_cards:
            messagebox.showerror("Card Not Found", f"No JPG/JPEG card found for player {number}.")
            return

        # Finish the previous player's decision before moving to another card.
        if self.current_player_number is not None:
            self.close_viewer()

        # Reopening a player starts a fresh decision; the most recent button
        # press will determine the final category.
        self.sold.discard(number)
        self.unsold.discard(number)
        self.indecisive.discard(number)
        self.opened.add(number)
        self.pending.add(number)
        self.update_lists()
        self.show_card(number)

    def record_result(self, result):
        """Apply the latest SOLD/UNSOLD button press to the current player."""
        number = self.current_player_number
        if number is None or not self.viewer or not self.viewer.winfo_exists():
            return

        self.opened.add(number)
        self.pending.discard(number)
        self.sold.discard(number)
        self.unsold.discard(number)
        self.indecisive.discard(number)

        if result == "SOLD":
            self.sold.add(number)
        else:
            self.unsold.add(number)

        self.update_lists()
        self.show_result_overlay(result)

    def show_card(self, number):
        image_path = self.available_cards[number]

        try:
            image = Image.open(image_path).convert("RGB")

        except Exception as error:
            messagebox.showerror(
                "Image Error",
                f"Could not open player card:\n{error}"
            )
            return

        # Close an existing viewer before opening another
        if self.viewer:
            self.close_viewer()

        self.viewer = tk.Toplevel(self.root)
        self.current_player_number = number
        self.viewer.title(f"Player {number}")
        self.viewer.configure(bg="black")
        self.viewer.protocol("WM_DELETE_WINDOW", self.close_viewer)

        self.viewer.bind(
            "<Escape>",
            self.close_viewer
        )

        monitor = None

        if get_monitors:
            try:
                monitors = get_monitors()

                if len(monitors) > 1:
                    monitor = monitors[1]

            except Exception:
                monitor = None

        if monitor:
            self.viewer.geometry(
                f"{monitor.width}x{monitor.height}"
                f"+{monitor.x}+{monitor.y}"
            )
        else:
            self.viewer.attributes("-fullscreen", True)

        self.viewer.update_idletasks()

        screen_width = self.viewer.winfo_width()
        screen_height = self.viewer.winfo_height()

        if screen_width <= 1:
            screen_width = self.root.winfo_screenwidth()

        if screen_height <= 1:
            screen_height = self.root.winfo_screenheight()

        image.thumbnail(
            (screen_width - 40, screen_height - 40),
            Image.Resampling.LANCZOS
        )

        self.viewer_image = ImageTk.PhotoImage(image)

        image_label = tk.Label(
            self.viewer,
            image=self.viewer_image,
            bg="black"
        )
        image_label.pack(expand=True)

        self.viewer.focus_force()

        if self.close_viewer_button:
            self.close_viewer_button.config(state="normal")
        if self.sold_button:
            self.sold_button.config(state="normal")
        if self.unsold_button:
            self.unsold_button.config(state="normal")

    # ================================================
    # SOLD / UNSOLD RESULT OVERLAY
    # ================================================

    def show_result_overlay(self, result):
        """Show a short animated result banner over the current player card."""
        if not self.viewer or not self.viewer.winfo_exists():
            return

        # Cancel an earlier animation if another result is triggered.
        if self.overlay_after_id is not None:
            try:
                self.root.after_cancel(self.overlay_after_id)
            except tk.TclError:
                pass
            self.overlay_after_id = None

        if self.overlay_widget is not None:
            try:
                self.overlay_widget.destroy()
            except tk.TclError:
                pass
            self.overlay_widget = None

        is_sold = result == "SOLD"
        banner_color = "#087f45" if is_sold else "#a51d2d"
        subtitle = (
            f"PLAYER {self.current_player_number}  •  AUCTION RESULT"
            if self.current_player_number is not None
            else "AUCTION RESULT"
        )

        banner = tk.Frame(
            self.viewer,
            bg=banner_color,
            highlightbackground="#ffffff",
            highlightthickness=2
        )
        banner.place(
            relx=0.5,
            rely=-0.25,
            anchor="center",
            relwidth=0.66,
            height=155
        )
        banner.lift()
        self.overlay_widget = banner

        tk.Label(
            banner,
            text=f"{result}!",
            bg=banner_color,
            fg="#ffffff",
            font=("Arial", 48, "bold")
        ).pack(pady=(17, 0))

        tk.Label(
            banner,
            text=subtitle,
            bg=banner_color,
            fg="#ffffff",
            font=("Arial", 13, "bold")
        ).pack(pady=(0, 12))

        self._animate_result_overlay(banner, 0, "in")

    def _animate_result_overlay(self, banner, step, direction):
        if not self.viewer or not self.viewer.winfo_exists():
            return
        if not banner.winfo_exists():
            return

        steps = 12

        if direction == "in":
            y = -0.25 + (0.75 * step / steps)
            banner.place_configure(rely=y)
            if step < steps:
                self.overlay_after_id = self.root.after(
                    22,
                    lambda: self._animate_result_overlay(
                        banner, step + 1, "in"
                    )
                )
            else:
                self.overlay_after_id = self.root.after(
                    2300,
                    lambda: self._animate_result_overlay(
                        banner, 0, "out"
                    )
                )
        else:
            y = 0.5 + (0.75 * step / steps)
            banner.place_configure(rely=y)
            if step < steps:
                self.overlay_after_id = self.root.after(
                    22,
                    lambda: self._animate_result_overlay(
                        banner, step + 1, "out"
                    )
                )
            else:
                try:
                    banner.destroy()
                except tk.TclError:
                    pass
                self.overlay_widget = None
                self.overlay_after_id = None

    def close_viewer(self, event=None):
        number = self.current_player_number

        # If no SOLD/UNSOLD button was pressed, classify the player as
        # indecisive when their card is closed or the next card is opened.
        if number is not None and number in self.pending:
            self.pending.discard(number)
            self.sold.discard(number)
            self.unsold.discard(number)
            self.indecisive.add(number)
            self.update_lists()

        if self.overlay_after_id is not None:
            try:
                self.root.after_cancel(self.overlay_after_id)
            except tk.TclError:
                pass
            self.overlay_after_id = None

        if self.overlay_widget is not None:
            try:
                self.overlay_widget.destroy()
            except tk.TclError:
                pass
            self.overlay_widget = None

        if self.viewer:
            try:
                self.viewer.destroy()
            except tk.TclError:
                pass
            self.viewer = None
            self.viewer_image = None

        if self.close_viewer_button:
            self.close_viewer_button.config(state="disabled")
        if self.sold_button:
            self.sold_button.config(state="disabled")
        if self.unsold_button:
            self.unsold_button.config(state="disabled")

        self.current_player_number = None

        if getattr(self, "player_entry", None):
            try:
                if self.player_entry.winfo_exists():
                    self.player_entry.delete(0, tk.END)
                    self.player_entry.focus_set()
            except tk.TclError:
                pass

    # ================================================
    # END AUCTION
    # ================================================

    def end_auction(self):
        answer = messagebox.askyesno(
            "End Auction?",
            "Are you sure you want to end this auction?\n\n"
            "The saved progress and auction name for this "
            "card directory will be cleared.\n\n"
            "This cannot be undone."
        )

        if not answer:
            return

        # Close the active card first. This may save an unresolved player as
        # indecisive; the session is then removed permanently below.
        if self.viewer:
            self.close_viewer()

        key = self.session_key()
        if key in self.state:
            del self.state[key]
        self.save_state_file()

        self.directory = None
        self.max_players = 0
        self.auction_name = ""
        # opened = every player called at least once.
        # pending = called players whose result has not been decided yet.
        self.opened = set()
        self.pending = set()
        self.sold = set()
        self.unsold = set()
        self.indecisive = set()
        self.available_cards = {}

        self.show_setup()

    # ================================================
    # GENERAL
    # ================================================

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def on_close(self):
        # Closing the application also finishes an active card decision.
        if self.viewer:
            self.close_viewer()
        self.save_session()
        self.root.destroy()


# ================================================
# RUN APPLICATION
# ================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = CricketAuction(root)

    root.protocol(
        "WM_DELETE_WINDOW",
        app.on_close
    )

    root.mainloop()
"""Built-in pure-MIT 24x24 geometric vector icon library for uiforge-mcp.

Every icon is authored directly as clean 24x24 SVG path commands (zero external copyright or
third-party license dependencies). Icons instantiate as editable native ``path`` elements on any
canvas, so they inherit PBR materials, gradients, strokes, glows, animations and vector exports.
"""

from __future__ import annotations

import re
from typing import Any

# Each entry: (svg_path_d, default_mode ["stroke"|"fill"], tags_csv)
_RAW_ICONS: dict[str, tuple[str, str, str]] = {
    # --- Navigation & Core UI ---
    "home": ("M3 10.5 L12 3 L21 10.5 V20 A1 1 0 0 1 20 21 H15 V14 H9 V21 H4 A1 1 0 0 1 3 20 Z", "stroke", "nav,house,main"),
    "menu": ("M3 6 H21 M3 12 H21 M3 18 H21", "stroke", "nav,hamburger,bars"),
    "close": ("M6 6 L18 18 M18 6 L6 18", "stroke", "nav,x,cancel,dismiss"),
    "x": ("M6 6 L18 18 M18 6 L6 18", "stroke", "nav,close,cancel"),
    "check": ("M4 12.5 L9.5 18 L20 6.5", "stroke", "action,ok,done,confirm"),
    "plus": ("M12 5 V19 M5 12 H19", "stroke", "action,add,new,create"),
    "minus": ("M5 12 H19", "stroke", "action,remove,subtract"),
    "search": ("M11 4 A7 7 0 1 0 11 18 A7 7 0 1 0 11 4 Z M16.2 16.2 L21 21", "stroke", "ui,find,magnifier"),
    "filter": ("M3 5 H21 L14 13 V19 L10 21 V13 Z", "stroke", "ui,funnel,sort"),
    "sort": ("M4 7 H14 M4 12 H11 M4 17 H8 M17 5 V19 M14 16 L17 19 L20 16", "stroke", "ui,order,list"),
    "refresh": ("M20 12 A8 8 0 1 1 17.5 6.2 M20 4 V9 H15", "stroke", "action,reload,sync"),
    "undo": ("M9 7 L4 12 L9 17 M4 12 H15 A5 5 0 0 1 15 22 H13", "stroke", "action,back,history"),
    "redo": ("M15 7 L20 12 L15 17 M20 12 H9 A5 5 0 0 0 9 22 H11", "stroke", "action,forward,history"),
    "arrow_up": ("M12 19 V5 M6 11 L12 5 L18 11", "stroke", "nav,direction"),
    "arrow_down": ("M12 5 V19 M6 13 L12 19 L18 13", "stroke", "nav,direction"),
    "arrow_left": ("M19 12 H5 M11 6 L5 12 L11 18", "stroke", "nav,back,direction"),
    "arrow_right": ("M5 12 H19 M13 6 L19 12 L13 18", "stroke", "nav,next,direction"),
    "chevron_up": ("M6 15 L12 9 L18 15", "stroke", "nav,caret,collapse"),
    "chevron_down": ("M6 9 L12 15 L18 9", "stroke", "nav,caret,dropdown,expand"),
    "chevron_left": ("M15 6 L9 12 L15 18", "stroke", "nav,caret,prev"),
    "chevron_right": ("M9 6 L15 12 L9 18", "stroke", "nav,caret,next"),
    "external_link": ("M14 4 H20 V10 M20 4 L10 14 M18 14 V19 A1 1 0 0 1 17 20 H5 A1 1 0 0 1 4 19 V7 A1 1 0 0 1 5 6 H10", "stroke", "nav,open,url"),
    "download": ("M12 3 V15 M7 10 L12 15 L17 10 M4 18 V20 H20 V18", "stroke", "action,save,export"),
    "upload": ("M12 15 V3 M7 8 L12 3 L17 8 M4 18 V20 H20 V18", "stroke", "action,import"),
    "share": ("M18 5 A2.5 2.5 0 1 0 18 10 A2.5 2.5 0 1 0 18 5 Z M6 9.5 A2.5 2.5 0 1 0 6 14.5 A2.5 2.5 0 1 0 6 9.5 Z M18 14 A2.5 2.5 0 1 0 18 19 A2.5 2.5 0 1 0 18 14 Z M8.3 10.9 L15.7 8.1 M8.3 13.1 L15.7 15.9", "stroke", "action,social"),
    "copy": ("M9 9 H20 V20 H9 Z M5 15 H4 V4 H15 V5", "stroke", "action,clipboard,duplicate"),
    "trash": ("M4 6 H20 M9 6 V4 H15 V6 M6 6 L7 20 H17 L18 6 M10 10 V16 M14 10 V16", "stroke", "action,delete,remove"),
    "edit": ("M4 20 H8 L19 9 L15 5 L4 16 Z M13.5 6.5 L17.5 10.5", "stroke", "action,pencil,write"),
    "save": ("M5 3 H16 L20 7 V20 H5 Z M8 3 V9 H15 V3 M8 14 H17 V20 H8 Z", "stroke", "action,floppy,disk"),
    "more_horiz": ("M5 12 A1.5 1.5 0 1 0 5 12.01 M12 12 A1.5 1.5 0 1 0 12 12.01 M19 12 A1.5 1.5 0 1 0 19 12.01", "stroke", "ui,dots,ellipsis"),
    "more_vert": ("M12 5 A1.5 1.5 0 1 0 12 5.01 M12 12 A1.5 1.5 0 1 0 12 12.01 M12 19 A1.5 1.5 0 1 0 12 19.01", "stroke", "ui,dots,kebab"),
    "maximize": ("M4 9 V4 H9 M15 4 H20 V9 M20 15 V20 H15 M9 20 H4 V15", "stroke", "ui,fullscreen,expand"),
    "minimize": ("M9 4 V9 H4 M15 4 V9 H20 M20 15 H15 V20 M4 15 H9 V20", "stroke", "ui,collapse,shrink"),

    # --- Settings, Security, Status & System ---
    "settings": ("M12 8.5 A3.5 3.5 0 1 0 12 15.5 A3.5 3.5 0 1 0 12 8.5 Z M12 2.5 V5 M12 19 V21.5 M4.8 4.8 L6.8 6.8 M17.2 17.2 L19.2 19.2 M2.5 12 H5 M19 12 H21.5 M4.8 19.2 L6.8 17.2 M17.2 6.8 L19.2 4.8 M12 5.5 A6.5 6.5 0 1 0 12 18.5 A6.5 6.5 0 1 0 12 5.5 Z", "stroke", "ui,gear,cog,config"),
    "gear": ("M12 8.5 A3.5 3.5 0 1 0 12 15.5 A3.5 3.5 0 1 0 12 8.5 Z M12 2.5 V5 M12 19 V21.5 M4.8 4.8 L6.8 6.8 M17.2 17.2 L19.2 19.2 M2.5 12 H5 M19 12 H21.5 M4.8 19.2 L6.8 17.2 M17.2 6.8 L19.2 4.8 M12 5.5 A6.5 6.5 0 1 0 12 18.5 A6.5 6.5 0 1 0 12 5.5 Z", "stroke", "ui,settings,cog"),
    "sliders": ("M4 6 H20 M4 12 H20 M4 18 H20 M9 4 V8 M15 10 V14 M11 16 V20", "stroke", "ui,controls,mixer,tune"),
    "eye": ("M2 12 C5 6.5 8.5 5 12 5 C15.5 5 19 6.5 22 12 C19 17.5 15.5 19 12 19 C8.5 19 5 17.5 2 12 Z M12 9 A3 3 0 1 0 12 15 A3 3 0 1 0 12 9 Z", "stroke", "ui,view,visible,preview"),
    "eye_off": ("M3 3 L21 21 M10.5 5.2 C11 5.1 11.5 5 12 5 C15.5 5 19 6.5 22 12 C20.8 14.2 19.3 15.9 17.6 17 M6.4 7 C4.6 8.2 3.2 9.9 2 12 C5 17.5 8.5 19 12 19 C13.2 19 14.3 18.7 15.4 18.2", "stroke", "ui,hide,hidden,password"),
    "lock": ("M6 11 H18 V20 H6 Z M8 11 V7.5 A4 4 0 0 1 16 7.5 V11 M12 14.5 V17", "stroke", "security,locked,private"),
    "unlock": ("M6 11 H18 V20 H6 Z M8 11 V7.5 A4 4 0 0 1 15.5 5.5 M12 14.5 V17", "stroke", "security,open"),
    "key": ("M8 15 A4.5 4.5 0 1 1 12.1 12.5 L21 12.5 V15.5 H18.5 V13.5 H16 V16 H14 V13.5", "stroke", "security,rpg,access"),
    "bell": ("M6 16 V10 A6 6 0 0 1 18 10 V16 L20 18 H4 Z M10 20 A2 2 0 0 0 14 20", "stroke", "ui,notification,alert"),
    "bell_off": ("M3 3 L21 21 M8.5 5.2 A6 6 0 0 1 18 10 V14.5 M6 10 V16 L4 18 H16 M10 20 A2 2 0 0 0 14 20", "stroke", "ui,mute,notification"),
    "info": ("M12 3 A9 9 0 1 0 12 21 A9 9 0 1 0 12 3 Z M12 11 V16 M12 8 V8.1", "stroke", "status,about,help"),
    "warning": ("M12 3 L22 20 H2 Z M12 10 V14.5 M12 17 V17.2", "stroke", "status,alert,caution"),
    "error": ("M12 3 A9 9 0 1 0 12 21 A9 9 0 1 0 12 3 Z M9 9 L15 15 M15 9 L9 15", "stroke", "status,fail,danger"),
    "check_circle": ("M12 3 A9 9 0 1 0 12 21 A9 9 0 1 0 12 3 Z M8.5 12.3 L11 14.8 L16 9.5", "stroke", "status,success,verified"),
    "help": ("M12 3 A9 9 0 1 0 12 21 A9 9 0 1 0 12 3 Z M9.5 9.5 A2.5 2.5 0 0 1 14.5 9.5 C14.5 11.5 12 11.8 12 14 M12 17 V17.2", "stroke", "status,question,faq"),
    "user": ("M12 4 A4 4 0 1 0 12 12 A4 4 0 1 0 12 4 Z M4.5 20.5 C5.5 16.5 8.2 15 12 15 C15.8 15 18.5 16.5 19.5 20.5", "stroke", "social,profile,avatar,player"),
    "users": ("M9 5 A3.5 3.5 0 1 0 9 12 A3.5 3.5 0 1 0 9 5 Z M3 20 C3.8 16.5 6 15 9 15 C12 15 14.2 16.5 15 20 M16 6 A3 3 0 1 1 16 12 M16.5 15 C19 15.3 20.5 16.8 21 20", "stroke", "social,party,team,guild"),
    "mail": ("M3 6 H21 V18 H3 Z M3 7 L12 13.5 L21 7", "stroke", "comm,email,inbox"),
    "chat": ("M4 5 H20 V16 H9 L4 20 Z M8 9.5 H16 M8 12.5 H13", "stroke", "comm,message,bubble"),
    "calendar": ("M4 6 H20 V20 H4 Z M4 10 H20 M8 3 V7 M16 3 V7", "stroke", "time,date,event"),
    "clock": ("M12 3 A9 9 0 1 0 12 21 A9 9 0 1 0 12 3 Z M12 7 V12 L15.5 14", "stroke", "time,timer,schedule"),
    "folder": ("M3 6 H9 L11 8 H21 V19 H3 Z", "stroke", "file,directory,project"),
    "file": ("M6 3 H14 L19 8 V21 H6 Z M14 3 V8 H19", "stroke", "file,document,page"),
    "code": ("M8 8 L3 12 L8 16 M16 8 L21 12 L16 16 M13.5 5 L10.5 19", "stroke", "dev,script,programming"),
    "terminal": ("M4 5 H20 V19 H4 Z M7 10 L10 12.5 L7 15 M12 15 H16", "stroke", "dev,console,cli"),
    "database": ("M5 6 C5 4.3 8.1 3 12 3 C15.9 3 19 4.3 19 6 C19 7.7 15.9 9 12 9 C8.1 9 5 7.7 5 6 Z M5 6 V18 C5 19.7 8.1 21 12 21 C15.9 21 19 19.7 19 18 V6 M5 12 C5 13.7 8.1 15 12 15 C15.9 15 19 13.7 19 12", "stroke", "dev,storage,server"),
    "cloud": ("M7 18 H18 A4 4 0 0 0 18.5 10.1 A5.5 5.5 0 0 0 7.8 8.8 A4.2 4.2 0 0 0 7 18 Z", "stroke", "system,sync,online"),
    "globe": ("M12 3 A9 9 0 1 0 12 21 A9 9 0 1 0 12 3 Z M3 12 H21 M12 3 C14.8 6 14.8 18 12 21 C9.2 18 9.2 6 12 3 Z", "stroke", "web,world,language,i18n"),
    "wifi": ("M4 9.5 C8.5 5.5 15.5 5.5 20 9.5 M7 13 C9.8 10.5 14.2 10.5 17 13 M10 16.5 C11.2 15.5 12.8 15.5 14 16.5 M12 19.5 V19.6", "stroke", "system,network,signal"),
    "battery": ("M3 8 H18 V16 H3 Z M18 10.5 H21 V13.5 H18 M6 10.5 H13 V13.5 H6 Z", "stroke", "system,power,charge"),
    "power": ("M12 3 V11 M7.2 6.2 A7.5 7.5 0 1 0 16.8 6.2", "stroke", "system,shutdown,exit,quit"),
    "sun": ("M12 8 A4 4 0 1 0 12 16 A4 4 0 1 0 12 8 Z M12 2.5 V5 M12 19 V21.5 M2.5 12 H5 M19 12 H21.5 M5.3 5.3 L7.1 7.1 M16.9 16.9 L18.7 18.7 M18.7 5.3 L16.9 7.1 M7.1 16.9 L5.3 18.7", "stroke", "theme,light,day,brightness"),
    "moon": ("M19 14.5 A7.5 7.5 0 0 1 9.5 5 A7.5 7.5 0 1 0 19 14.5 Z", "stroke", "theme,dark,night"),
    "palette": ("M12 3 A9 9 0 1 0 16 20 C14.5 20 14 19 14 18 C14 17 14.8 16 16 16 H18 A3 3 0 0 0 21 13 A9 9 0 0 0 12 3 Z M8 10 A1 1 0 1 0 8 10.1 M12 7.5 A1 1 0 1 0 12 7.6 M16 10 A1 1 0 1 0 16 10.1 M7.5 14.5 A1 1 0 1 0 7.5 14.6", "stroke", "design,color,theme"),
    "layers": ("M12 3 L21 8 L12 13 L3 8 Z M3 12.5 L12 17.5 L21 12.5 M3 16.5 L12 21.5 L21 16.5", "stroke", "design,stack"),
    "grid": ("M4 4 H10 V10 H4 Z M14 4 H20 V10 H14 Z M4 14 H10 V20 H4 Z M14 14 H20 V20 H14 Z", "stroke", "ui,inventory,apps"),
    "list": ("M9 6 H20 M9 12 H20 M9 18 H20 M4.5 6 H5 M4.5 12 H5 M4.5 18 H5", "stroke", "ui,rows,items"),
    "bookmark": ("M6 4 H18 V21 L12 16.5 L6 21 Z", "stroke", "ui,save,favorite"),
    "tag": ("M4 4 H11 L20 13 L13 20 L4 11 Z M8.5 8.5 A1 1 0 1 0 8.5 8.6", "stroke", "ui,label,price"),
    "pin": ("M9 4 H15 L14 10 L18 14 H6 L10 10 Z M12 14 V21", "stroke", "ui,anchor,sticky"),
    "link": ("M10 14 A4 4 0 0 1 10 8.5 L12.5 6 A4 4 0 0 1 18 11.5 L16.5 13 M14 10 A4 4 0 0 1 14 15.5 L11.5 18 A4 4 0 0 1 6 12.5 L7.5 11", "stroke", "ui,chain,url"),
    "camera": ("M3 8 H7 L9 5 H15 L17 8 H21 V19 H3 Z M12 10 A3.5 3.5 0 1 0 12 17 A3.5 3.5 0 1 0 12 10 Z", "stroke", "media,photo,screenshot"),
    "image": ("M4 5 H20 V19 H4 Z M8.5 9.5 A1.5 1.5 0 1 0 8.5 9.6 M4 16 L9.5 11.5 L13.5 15 L16.5 12.5 L20 16", "stroke", "media,picture,gallery"),
    "mic": ("M9 5 A3 3 0 0 1 15 5 V12 A3 3 0 0 1 9 12 Z M6 11 A6 6 0 0 0 18 11 M12 17 V21 M9 21 H15", "stroke", "audio,voice,record"),
    "mic_off": ("M3 3 L21 21 M9 9 V12 A3 3 0 0 0 14.2 14 M15 11 V5 A3 3 0 0 0 9.4 3.5 M6 11 A6 6 0 0 0 16.5 15 M12 17 V21 M9 21 H15", "stroke", "audio,mute,voice"),

    # --- Media, Audio & Devices ---
    "play": ("M6 4.5 L19.5 12 L6 19.5 Z", "fill", "media,start,video,game"),
    "pause": ("M6 5 H10 V19 H6 Z M14 5 H18 V19 H14 Z", "fill", "media,hold,wait"),
    "stop": ("M6 6 H18 V18 H6 Z", "fill", "media,end"),
    "skip_next": ("M5 5 L15 12 L5 19 Z M18 5 V19", "fill", "media,forward"),
    "skip_prev": ("M19 5 L9 12 L19 19 Z M6 5 V19", "fill", "media,back"),
    "volume": ("M4 9 H8 L13 5 V19 L8 15 H4 Z M16.5 9 A4.5 4.5 0 0 1 16.5 15 M19 6.5 A8 8 0 0 1 19 17.5", "stroke", "audio,sound,speaker"),
    "volume_mute": ("M4 9 H8 L13 5 V19 L8 15 H4 Z M16.5 9.5 L21 14.5 M21 9.5 L16.5 14.5", "stroke", "audio,silent,sfx"),
    "music": ("M9 18 V6 L20 4 V16 M9 18 A2.5 2.5 0 1 1 6.5 15.5 A2.5 2.5 0 0 1 9 18 Z M20 16 A2.5 2.5 0 1 1 17.5 13.5 A2.5 2.5 0 0 1 20 16 Z", "stroke", "audio,song,bgm"),
    "headphones": ("M4 14 V12 A8 8 0 0 1 20 12 V14 M4 14 H7 V19 H4 Z M17 14 H20 V19 H17 Z", "stroke", "audio,headset"),
    "gamepad": ("M6 8 H18 A4 4 0 0 1 21.8 13 L21 17 A2.5 2.5 0 0 1 16.8 18 L14.5 16 H9.5 L7.2 18 A2.5 2.5 0 0 1 3 17 L2.2 13 A4 4 0 0 1 6 8 Z M7 11 V14 M5.5 12.5 H8.5 M16 11.5 H16.1 M18 13.5 H18.1", "stroke", "game,controller,input"),
    "keyboard": ("M3 6 H21 V18 H3 Z M6 10 H7 M10 10 H11 M14 10 H15 M18 10 H18.5 M8 14 H16", "stroke", "input,keys,pc"),
    "monitor": ("M3 4 H21 V16 H3 Z M9 20 H15 M12 16 V20", "stroke", "device,screen,desktop,display"),
    "smartphone": ("M7 3 H17 V21 H7 Z M11 18 H13", "stroke", "device,mobile,phone"),

    # --- Game HUD, RPG, Combat, Racing & Sci-Fi ---
    "heart": ("M12 20.5 C12 20.5 4 15.2 4 9.2 A4.5 4.5 0 0 1 12 6.5 A4.5 4.5 0 0 1 20 9.2 C20 15.2 12 20.5 12 20.5 Z", "fill", "game,hp,health,life,like"),
    "heart_outline": ("M12 20.5 C12 20.5 4 15.2 4 9.2 A4.5 4.5 0 0 1 12 6.5 A4.5 4.5 0 0 1 20 9.2 C20 15.2 12 20.5 12 20.5 Z", "stroke", "game,hp,health,life"),
    "shield": ("M12 3 L20 6 V11.5 C20 16.5 16.5 19.8 12 21.5 C7.5 19.8 4 16.5 4 11.5 V6 Z", "stroke", "game,armor,defense,security"),
    "shield_fill": ("M12 3 L20 6 V11.5 C20 16.5 16.5 19.8 12 21.5 C7.5 19.8 4 16.5 4 11.5 V6 Z", "fill", "game,armor,defense"),
    "sword": ("M19 3 L21 5 L11 15 L9 13 Z M7 11 L13 17 M8 16 L4 20 L3 19 L7 15", "stroke", "game,rpg,weapon,attack,combat"),
    "axe": ("M5 19 L17 7 M13 4 C17 4 20 7 20 11 C17.5 11.5 15 10.5 13.5 9 Z", "stroke", "game,rpg,weapon,combat"),
    "bow": ("M5 19 C5 10 10 5 19 5 M5 19 L19 5 M13 11 L20 4 M16 4 H20 V8", "stroke", "game,rpg,ranged,archery"),
    "wand": ("M4 20 L15 9 M15 5 V2.5 M15 12.5 V10 M11 8.5 H8.5 M21.5 8.5 H19 M18 5.5 L19.8 3.7", "stroke", "game,magic,spell,wizard"),
    "skull": ("M12 3 C7.5 3 4.5 6.2 4.5 10.2 C4.5 12.8 5.8 14.8 7.5 16 V19.5 H16.5 V16 C18.2 14.8 19.5 12.8 19.5 10.2 C19.5 6.2 16.5 3 12 3 Z M9 11 A1.4 1.4 0 1 0 9 11.1 M15 11 A1.4 1.4 0 1 0 15 11.1 M10 19.5 V17 M14 19.5 V17", "stroke", "game,death,boss,danger,enemy"),
    "crown": ("M3 18 L5 7 L9.5 12 L12 5 L14.5 12 L19 7 L21 18 Z M4 20 H20", "stroke", "game,king,vip,rank,royal"),
    "gem": ("M6 4 H18 L22 9 L12 21 L2 9 Z M2 9 H22 M12 21 L8.5 9 L12 4 L15.5 9 Z", "stroke", "game,diamond,currency,premium"),
    "coin": ("M12 3 A9 9 0 1 0 12 21 A9 9 0 1 0 12 3 Z M12 7 V17 M14.5 9.5 C14.5 8.4 13.4 8 12 8 C10.6 8 9.5 8.6 9.5 9.6 C9.5 11 14.5 11 14.5 13.2 C14.5 14.5 13.4 15.2 12 15.2 C10.6 15.2 9.5 14.6 9.5 13.6", "stroke", "game,gold,money,currency"),
    "chest": ("M3 9 H21 V19 H3 Z M3 9 C3 5.5 6 4.5 12 4.5 C18 4.5 21 5.5 21 9 M3 13 H21 M10 11 H14 V15 H10 Z", "stroke", "game,loot,treasure,inventory"),
    "backpack": ("M6 9 A6 6 0 0 1 18 9 V20 H6 Z M9 6 V4 H15 V6 M8 14 H16 V18 H8 Z M4 11 H6 V17 H4 Z M18 11 H20 V17 H18 Z", "stroke", "game,inventory,bag,items"),
    "potion": ("M9 3 H15 M10 3 V8 L5.5 15.5 A3.5 3.5 0 0 0 8.5 20.5 H15.5 A3.5 3.5 0 0 0 18.5 15.5 L14 8 V3 M7.5 14.5 H16.5", "stroke", "game,rpg,mana,heal,flask"),
    "flame": ("M12 2.5 C14.5 6 18.5 8.5 18.5 13.5 A6.5 6.5 0 0 1 5.5 13.5 C5.5 10.5 7.2 8.2 9 6.5 C9 9 10.5 9.8 11.2 9.2 C10.5 6.8 11.2 4.5 12 2.5 Z", "stroke", "game,fire,burn,streak,hot"),
    "bolt": ("M13 2.5 L4.5 13.5 H11.5 L10.5 21.5 L19.5 10.5 H12.5 Z", "fill", "game,lightning,energy,stamina,power"),
    "snowflake": ("M12 3 V21 M3 12 H21 M5.6 5.6 L18.4 18.4 M18.4 5.6 L5.6 18.4 M9.5 4.5 L12 7 L14.5 4.5 M9.5 19.5 L12 17 L14.5 19.5", "stroke", "game,ice,frost,cold"),
    "droplet": ("M12 3 C12 3 5.5 10.2 5.5 14.5 A6.5 6.5 0 0 0 18.5 14.5 C18.5 10.2 12 3 12 3 Z", "stroke", "game,water,mana,blood"),
    "leaf": ("M5 20 C5 10 10 4 20 4 C20 14 14 19 5 20 Z M5 20 L14 11", "stroke", "game,nature,eco,herb"),
    "star": ("M12 2.5 L14.9 8.6 L21.5 9.5 L16.7 14.1 L17.9 20.7 L12 17.5 L6.1 20.7 L7.3 14.1 L2.5 9.5 L9.1 8.6 Z", "fill", "game,rating,favorite,xp,rank"),
    "star_outline": ("M12 2.5 L14.9 8.6 L21.5 9.5 L16.7 14.1 L17.9 20.7 L12 17.5 L6.1 20.7 L7.3 14.1 L2.5 9.5 L9.1 8.6 Z", "stroke", "game,rating,favorite"),
    "trophy": ("M7 4 H17 V10 A5 5 0 0 1 7 10 Z M7 6 H4 V9 A3 3 0 0 0 7 11 M17 6 H20 V9 A3 3 0 0 1 17 11 M12 15 V19 M8 20 H16", "stroke", "game,achievement,win,leaderboard"),
    "medal": ("M8 3 L12 10 L16 3 M12 10 A5.5 5.5 0 1 0 12 21 A5.5 5.5 0 1 0 12 10 Z", "stroke", "game,award,badge,rank"),
    "flag": ("M5 3 V21 M5 4 H19 L16 9 L19 14 H5", "stroke", "game,quest,checkpoint,race"),
    "target": ("M12 3 A9 9 0 1 0 12 21 A9 9 0 1 0 12 3 Z M12 7 A5 5 0 1 0 12 17 A5 5 0 1 0 12 7 Z M12 10.5 A1.5 1.5 0 1 0 12 13.5 A1.5 1.5 0 1 0 12 10.5 Z", "stroke", "game,fps,aim,objective"),
    "crosshair": ("M12 4 A8 8 0 1 0 12 20 A8 8 0 1 0 12 4 Z M12 2 V6 M12 18 V22 M2 12 H6 M18 12 H22", "stroke", "game,fps,hud,scope,aim"),
    "compass": ("M12 3 A9 9 0 1 0 12 21 A9 9 0 1 0 12 3 Z M15.5 8.5 L13.2 13.2 L8.5 15.5 L10.8 10.8 Z", "stroke", "game,map,nav,explore"),
    "map": ("M3 6 L9 4 L15 6 L21 4 V18 L15 20 L9 18 L3 20 Z M9 4 V18 M15 6 V20", "stroke", "game,world,minimap,quest"),
    "map_pin": ("M12 21 C12 21 5.5 14.5 5.5 9.5 A6.5 6.5 0 1 1 18.5 9.5 C18.5 14.5 12 21 12 21 Z M12 7.5 A2 2 0 1 0 12 11.5 A2 2 0 1 0 12 7.5 Z", "stroke", "game,location,waypoint,marker"),
    "book": ("M4 4 H11 A3 3 0 0 1 14 7 V20 A2 2 0 0 0 12 18 H4 Z M20 4 H13 A3 3 0 0 0 10 7 V20 A2 2 0 0 1 12 18 H20 Z", "stroke", "game,codex,journal,lore,docs"),
    "scroll_icon": ("M6 4 H18 A2 2 0 0 1 20 6 V8 H17 V18 A2 2 0 0 1 15 20 H6 A2 2 0 0 1 4 18 V6 A2 2 0 0 1 6 4 Z M8 9 H14 M8 13 H14", "stroke", "game,quest,parchment,rpg"),
    "hammer": ("M14 4 L20 10 L17 13 L11 7 Z M13 10 L5 18 L6.5 19.5 L14.5 11.5", "stroke", "game,craft,build,forge"),
    "wrench": ("M14.7 6.3 A4.5 4.5 0 0 0 8.5 12.5 L4 17 L7 20 L11.5 15.5 A4.5 4.5 0 0 0 17.7 9.3 L15 12 L12 9 Z", "stroke", "game,repair,tool,mechanic"),
    "hourglass": ("M6 3 H18 M6 21 H18 M7 3 C7 8 12 10 12 12 C12 14 7 16 7 21 M17 3 C17 8 12 10 12 12 C12 14 17 16 17 21", "stroke", "game,cooldown,timer,wait"),
    "medkit": ("M3 7 H21 V19 H3 Z M9 7 V4 H15 V7 M12 10 V16 M9 13 H15", "stroke", "game,heal,health,fps,medic"),
    "ammo": ("M7 20 V9 L9 4 L11 9 V20 Z M13 20 V9 L15 4 L17 9 V20 Z M6 16 H18", "stroke", "game,fps,bullet,weapon"),
    "gauge": ("M4 17 A8.5 8.5 0 1 1 20 17 M12 15 L16.5 9.5 M12 14 A1.5 1.5 0 1 0 12 17 A1.5 1.5 0 1 0 12 14 Z", "stroke", "racing,speed,tachometer,telemetry"),
    "fuel": ("M5 4 H14 V20 H5 Z M7 7 H12 V11 H7 Z M14 8 H17 L19 10 V17 A1.5 1.5 0 0 1 16 17 V12 H14", "stroke", "racing,gas,tank,car"),
    "rocket": ("M12 3 C16 5 18 9 18 14 L14 18 L6 10 C6 9 8 5 12 3 Z M9 13 L5 17 M12 9 A1.5 1.5 0 1 0 12 9.1 M4 20 L7 19 L5 17 Z", "stroke", "scifi,launch,boost,space"),
    "cpu": ("M7 7 H17 V17 H7 Z M10 10 H14 V14 H10 Z M9 3 V7 M15 3 V7 M9 17 V21 M15 17 V21 M3 9 H7 M3 15 H7 M17 9 H21 M17 15 H21", "stroke", "scifi,tech,chip,hardware,gpu"),
    "sparkles": ("M12 3 L13.8 8.2 L19 10 L13.8 11.8 L12 17 L10.2 11.8 L5 10 L10.2 8.2 Z M18.5 15 L19.3 17.2 L21.5 18 L19.3 18.8 L18.5 21 L17.7 18.8 L15.5 18 L17.7 17.2 Z", "fill", "ai,magic,special,new,shine"),

    # --- Shop, Commerce & Communication ---
    "cart": ("M3 4 H6 L8 15 H18 L20.5 7 H7 M9.5 19 A1.2 1.2 0 1 0 9.5 19.1 M17 19 A1.2 1.2 0 1 0 17 19.1", "stroke", "shop,store,buy,ecommerce"),
    "bag": ("M5 8 H19 L20 20 H4 Z M9 8 V6 A3 3 0 0 1 15 6 V8", "stroke", "shop,store,inventory"),
    "credit_card": ("M3 6 H21 V18 H3 Z M3 10 H21 M7 14 H11", "stroke", "shop,pay,billing"),
    "wallet": ("M3 6 H19 V19 H3 Z M15 11 H21 V15 H15 Z M17.5 13 H17.6", "stroke", "shop,currency,money"),
    "gift": ("M4 9 H20 V20 H4 Z M3 9 H21 V12 H3 Z M12 9 V20 M12 9 C12 6 8 4 7.5 6.5 C7 8.5 10 9 12 9 C12 6 16 4 16.5 6.5 C17 8.5 14 9 12 9", "stroke", "shop,reward,daily,bonus"),
    "send": ("M21 3 L10 14 M21 3 L14.5 21 L10 14 L3 9.5 Z", "stroke", "comm,submit,chat"),
    "thumbs_up": ("M7 11 V20 H4 V11 Z M7 11 L11 4 C12.5 4 13.5 5 13 7 L12.5 10 H18.5 A2 2 0 0 1 20.4 12.4 L19 18.4 A2 2 0 0 1 17 20 H7", "stroke", "social,like,vote"),
    "phone": ("M6 3 H9 L11 8 L8.5 10 C9.8 12.5 11.5 14.2 14 15.5 L16 13 L21 15 V18 A2 2 0 0 1 19 20 C10.5 19.5 4.5 13.5 4 5 A2 2 0 0 1 6 3 Z", "stroke", "comm,call,contact"),
    "video": ("M3 7 H15 V17 H3 Z M15 10.5 L21 7.5 V16.5 L15 13.5 Z", "stroke", "media,call,stream,record"),
}

ICON_NAMES: tuple[str, ...] = tuple(sorted(_RAW_ICONS))

_TOKEN_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def list_icons(query: str | None = None) -> list[dict[str, Any]]:
    """List available built-in icons, optionally filtered by name or tag keyword."""
    q = (query or "").strip().lower()
    out: list[dict[str, Any]] = []
    for name in ICON_NAMES:
        _, mode, tags = _RAW_ICONS[name]
        if q and (q not in name and q not in tags):
            continue
        out.append({"name": name, "mode": mode, "tags": tags.split(",")})
    return out


def resolve_icon(name: str) -> tuple[str, str, str]:
    """Resolve an icon by exact name or normalized alias, returning (canonical_name, d_24, default_mode)."""
    key = re.sub(r"[\s\-]+", "_", str(name or "").strip().lower())
    if key in _RAW_ICONS:
        d, mode, _ = _RAW_ICONS[key]
        return key, d, mode
    # Prefix / tag match fallback if unique or close suggestion
    matches = [n for n in ICON_NAMES if key in n or key in _RAW_ICONS[n][2].split(",")]
    hint = f" Did you mean: {', '.join(matches[:8])}?" if matches else f" Available: {', '.join(ICON_NAMES[:15])}... ({len(ICON_NAMES)} total)"
    raise ValueError(f"Unknown icon '{name}'.{hint}")


def transform_svg_path_24(d: str, x: float, y: float, size: float) -> str:
    """Scale and translate an absolute 24x24 SVG path string into canvas coordinates."""
    s = float(size) / 24.0
    tokens = _TOKEN_RE.findall(d)
    out: list[str] = []
    i = 0
    cmd = ""

    def fmt(v: float) -> str:
        r = round(v, 3)
        return str(int(r)) if r == int(r) else f"{r:g}"

    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            out.append(cmd)
            i += 1
            continue
        if cmd in ("M", "L", "T"):
            px, py = float(tokens[i]), float(tokens[i + 1])
            out.extend([fmt(x + px * s), fmt(y + py * s)])
            i += 2
        elif cmd == "H":
            px = float(tokens[i])
            out.append(fmt(x + px * s))
            i += 1
        elif cmd == "V":
            py = float(tokens[i])
            out.append(fmt(y + py * s))
            i += 1
        elif cmd == "C":
            vals = [float(tokens[i + j]) for j in range(6)]
            out.extend([
                fmt(x + vals[0] * s), fmt(y + vals[1] * s),
                fmt(x + vals[2] * s), fmt(y + vals[3] * s),
                fmt(x + vals[4] * s), fmt(y + vals[5] * s),
            ])
            i += 6
        elif cmd in ("S", "Q"):
            vals = [float(tokens[i + j]) for j in range(4)]
            out.extend([
                fmt(x + vals[0] * s), fmt(y + vals[1] * s),
                fmt(x + vals[2] * s), fmt(y + vals[3] * s),
            ])
            i += 4
        elif cmd == "A":
            rx, ry = float(tokens[i]), float(tokens[i + 1])
            rot, laf, sf = tokens[i + 2], tokens[i + 3], tokens[i + 4]
            ex, ey = float(tokens[i + 5]), float(tokens[i + 6])
            out.extend([
                fmt(rx * s), fmt(ry * s), rot, laf, sf,
                fmt(x + ex * s), fmt(y + ey * s),
            ])
            i += 7
        else:
            out.append(tok)
            i += 1
    return " ".join(out)


def build_icon_element(name: str, x: float, y: float, size: float = 28.0, color: Any = "#f8fafc",
                       stroke_width: float = 2.0, filled: bool | None = None,
                       style: Any = None, **extra: Any) -> tuple[str, dict[str, Any]]:
    """Build a native 'path' element dict ready for Store.add_element.

    Keeps the SVG path in local [0..size] coordinates and stores absolute canvas x/y on the element
    so subsequent update_element(id, {"x": ..., "y": ...}) moves it to the exact position without
    double-offsetting.
    """
    cname, d24, default_mode = resolve_icon(name)
    sz = max(4.0, float(size))
    d_scaled = transform_svg_path_24(d24, 0.0, 0.0, sz)
    use_fill = (default_mode == "fill") if filled is None else bool(filled)

    st: dict[str, Any]
    if isinstance(style, dict):
        st = dict(style)
    elif isinstance(style, str):
        st = {"use": style}
    else:
        st = {}

    if use_fill:
        st.setdefault("fill", color)
    else:
        st.setdefault("fill", None)
        sw = max(0.5, float(stroke_width) * (sz / 24.0))
        st.setdefault("stroke", {"color": color, "width": round(sw, 2), "align": "center", "join": "round"})

    el: dict[str, Any] = {
        "d": d_scaled,
        "x": float(x),
        "y": float(y),
        "closed": False,
        "style": st,
        "note": f"icon:{cname}",
    }
    for k, v in extra.items():
        if v is not None:
            el[k] = v
    return cname, el

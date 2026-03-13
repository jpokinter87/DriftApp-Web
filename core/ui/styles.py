"""
Styles CSS pour l'interface Textual.
"""

CSS = """
Screen {
    layout: vertical;
    background: #0a0a0a;
    color: #bcbcbc;
    overflow-y: auto;
}
Header {
    background: #0a0a0a;
    color: #8a8a8a;
    dock: top;
}
Footer {
    background: #0a0a0a;
    color: #8a8a8a;
    dock: bottom;
}
Input {
    background: #111111;
    color: #bcbcbc;
    border: solid #262626;
    width: 100%;
    height: 3;
}
Input:focus {
    border: solid #552222;
}
Button {
    min-width: 18;
    margin: 0 1;
    height: 3;
    color: #e6e6e6;
}
Button.-success {
    background: #4a1a1a;
    color: #ffffff;
}
Button.-success:hover {
    background: #6a2a2a;
}
Button.-error {
    background: #6a2020;
    color: #ffffff;
}
Button.-error:hover {
    background: #7a2a2a;
}
Button.-primary {
    background: #3a2a1a;
    color: #ffffff;
}
Button.-primary:hover {
    background: #4a3625;
}

/* Conteneurs compacts */
#hardware_info {
    width: 100%;
    height: 3;
    border: solid #2a2a2a;
    padding: 0 1;
    color: #b0a080;       /* ambre doux */
    background: #14110e;
}

#input_container {
    width: 100%;
    height: 5;
    padding: 0 1;
    layout: horizontal;
    align: center middle;
    background: #0a0a0a;
}
#prompt {
    width: auto;
    color: #c8c8c8;
    margin-right: 1;
}
#input_obj {
    width: 1fr;
}

#row_azimut {
    width: 100%;
    height: 5;
    padding: 0 1;
    layout: horizontal;
    align: center middle;
    background: #0a0a0a;
}
#prompt_azimut {
    width: auto;
    color: #c8c8c8;
    margin-right: 1;
}
#input_azimut {
    width: 1fr;
}

#button_row {
    width: 100%;
    height: 5;
    layout: horizontal;
    align: center middle;
    padding: 0 1;
}

#status {
    width: 100%;
    height: 3;
    border: solid #332020;
    padding: 0 1;
    color: #c07a6a;       /* rouge atténué */
    background: #120606;
}

#parallax_info {
    width: 100%;
    height: 3;
    border: solid #2f2620;
    padding: 0 1;
    color: #b89a6a;       /* ambre atténué */
    background: #120f0b;
}

#sync_info {
    width: 100%;
    height: 3;
    border: solid #232323;
    padding: 0 1;
    color: #c8c8c8;
    background: #0a0a0a;
}

#log {
    width: 100%;
    height: 1fr;
    border: solid #232323;
    padding: 0 1;
    overflow-y: auto;
    color: #c8c8c8;
    background: #0a0a0a;
}

/* Modales */
#config_container, #confirm_container {
    width: 50;
    height: auto;
    border: solid #3a3a3a;
    background: #111111;
    padding: 1;
    layout: vertical;
}
#config_title, #confirm_msg {
    text-align: center;
    text-style: bold;
    color: #c07a6a;
    margin-bottom: 1;
}
#confirm_msg {
    color: #c07a6a;
}
#lbl_seuil_cfg, #lbl_int_cfg {
    color: #c8c8c8;
}
#input_seuil_cfg, #input_intervalle_cfg {
    margin-bottom: 1;
}
#cfg_buttons, #confirm_buttons {
    width: 100%;
    height: auto;
    margin-top: 1;
    layout: horizontal;
    align: center middle;
}
"""

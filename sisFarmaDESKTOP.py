import sqlite3
import os
import tkinter as tk
import customtkinter as ctk
from tkinter import ttk, messagebox
from datetime import datetime

# =========================================================================
# CONFIGURAÇÃO GLOBAL DE APARÊNCIA E TEMA
# =========================================================================
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


# =========================================================================
# 1. BANCO DE DADOS (ARQUITETURA INTEGRADA E CORRIGIDA)
# =========================================================================
def conectar_bd():
    return sqlite3.connect("farmacia_hospitalar.db")


def inicializar_banco():
    conn = conectar_bd()
    cursor = conn.cursor()

    # CATÁLOGO DE MEDICAMENTOS
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS medicamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        principio_ativo TEXT,
        categoria TEXT,
        controlado INTEGER,
        codigo_barras TEXT UNIQUE
    )
    ''')

    # CATÁLOGO DE INSUMOS GERAIS
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS insumos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        especificacao TEXT,
        unidade_medida TEXT NOT NULL,
        grupo TEXT
    )
    ''')

    # LOTES DE MEDICAMENTOS
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS lotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        medicamento_id INTEGER,
        numero_lote TEXT NOT NULL,
        fabricante TEXT,
        data_fabricacao TEXT,
        validade TEXT NOT NULL,
        quantidade INTEGER NOT NULL,
        FOREIGN KEY(medicamento_id) REFERENCES medicamentos(id)
    )
    ''')

    # LOTES DE INSUMOS GERAIS
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS lotes_insumos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        insumo_id INTEGER,
        numero_lote TEXT NOT NULL,
        fabricante TEXT,
        validade TEXT NOT NULL,
        quantidade INTEGER NOT NULL,
        FOREIGN KEY(insumo_id) REFERENCES insumos(id)
    )
    ''')

    # MOVIMENTAÇÕES UNIFICADAS
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS movimentacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lote_id INTEGER,
        insumo_lote_id INTEGER,
        tipo TEXT NOT NULL,
        quantidade INTEGER NOT NULL,
        setor_destino TEXT,
        paciente_nome TEXT,
        prescricao_num TEXT,
        responsavel TEXT NOT NULL,
        data_movimentacao TEXT NOT NULL,
        FOREIGN KEY(lote_id) REFERENCES lotes(id),
        FOREIGN KEY(insumo_lote_id) REFERENCES lotes_insumos(id)
    )
    ''')

    # USUÁRIOS
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT UNIQUE,
        senha TEXT,
        perfil TEXT
    )
    ''')

    # REGISTROS DE TECNOVIGILÂNCIA (POP.FARM.019)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tecnovigilancia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lote_texto TEXT NOT NULL,
        tipo_ocorrencia TEXT NOT NULL,
        descricao TEXT NOT NULL,
        gravidade TEXT NOT NULL,
        conduta TEXT NOT NULL,
        data_registro TEXT NOT NULL,
        operador TEXT NOT NULL
    )
    ''')

    # GARANTIR USUÁRIO ADMINISTRADOR PADRÃO
    cursor.execute("SELECT * FROM usuarios WHERE usuario='admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO usuarios(usuario, senha, perfil) VALUES('admin', '123', 'Farmacêutico Chefe')")

    conn.commit()
    conn.close()


# =========================================================================
# 2. TELA DE LOGIN INTERATIVA
# =========================================================================
class Login:
    def __init__(self, master):
        self.master = master
        self.master.title("Acesso Restrito - SisFarma v.1.0")
        self.master.geometry("420x450")
        self.master.resizable(False, False)
        self.master.eval('tk::PlaceWindow . center')

        frame = ctk.CTkFrame(master=self.master, corner_radius=15)
        frame.pack(pady=30, padx=30, fill="both", expand=True)

        ctk.CTkLabel(frame, text="🔐 CAF HOSPITALAR", font=("Segoe UI", 22, "bold")).pack(pady=(30, 5))
        ctk.CTkLabel(frame, text="Controle Interno & Rastreabilidade", font=("Segoe UI", 12, "italic"),
                     text_color="gray").pack(pady=(0, 20))

        self.usuario = ctk.CTkEntry(frame, placeholder_text="Usuário ou Registro", width=260, height=40)
        self.usuario.pack(pady=10)

        self.senha = ctk.CTkEntry(frame, placeholder_text="Senha", show="*", width=260, height=40)
        self.senha.pack(pady=10)

        btn_login = ctk.CTkButton(frame, text="Autenticar no Sistema", width=260, height=45,
                                  font=("Segoe UI", 14, "bold"), command=self.verificar_login)
        btn_login.pack(pady=30)

    def verificar_login(self):
        u, s = self.usuario.get(), self.senha.get()
        db = conectar_bd()
        c = db.cursor()
        c.execute('SELECT usuario, perfil FROM usuarios WHERE usuario=? AND senha=?', (u, s))
        user = c.fetchone()
        db.close()

        if user:
            self.master.withdraw()
            root = ctk.CTk()
            app = SistemaHospitalar(root, user[0], user[1])
            root.mainloop()
            self.master.destroy()
        else:
            messagebox.showerror("Erro de Segurança", "Credenciais inválidas. Acesso negado.")


# =========================================================================
# MODULE AUXILIAR: MÓDULO DE TECNOVIGILÂNCIA DE ACORDO COM POP.FARM.019
# =========================================================================
class ModuloTecnovigilancia:
    def __init__(self, parent_frame, usuario_operador):
        self.frame = parent_frame
        self.operador = usuario_operador

        ctk.CTkLabel(self.frame, text="⚠️ Registro de Ocorrência de Tecnovigilância (POP.FARM.019)",
                     font=("Segoe UI", 18, "bold"), text_color="#c0392b").pack(pady=10, anchor="w")

        form = ctk.CTkFrame(self.frame)
        form.pack(fill="x", pady=10, padx=5)

        ctk.CTkLabel(form, text="Lote / Item Suspeito:").grid(row=0, column=0, padx=15, pady=10, sticky="e")
        self.entry_lote = ctk.CTkEntry(form, width=250, placeholder_text="Ex: Lote LOT2411 - Ambroxol")
        self.entry_lote.grid(row=0, column=1, padx=15, pady=10)

        ctk.CTkLabel(form, text="Tipo de Inconformidade:").grid(row=0, column=2, padx=15, pady=10, sticky="e")
        self.cb_tipo = ctk.CTkComboBox(form, values=["Desvio de Qualidade", "Queixa Técnica", "Efeito Adverso",
                                                     "Embalagem Violada"], width=250)
        self.cb_tipo.grid(row=0, column=3, padx=15, pady=10)

        ctk.CTkLabel(form, text="Gravidade:").grid(row=1, column=0, padx=15, pady=10, sticky="e")
        self.cb_gravidade = ctk.CTkComboBox(form, values=["Baixa", "Moderada", "Alta / Crítica"], width=250)
        self.cb_gravidade.grid(row=1, column=1, padx=15, pady=10)

        ctk.CTkLabel(form, text="Descrição Detalhada:").grid(row=2, column=0, padx=15, pady=10, sticky="ne")
        self.txt_desc = ctk.CTkEntry(form, width=640, placeholder_text="Descreva as alterações observadas...")
        self.txt_desc.grid(row=2, column=1, columnspan=3, padx=15, pady=10, sticky="w")

        ctk.CTkLabel(form, text="Conduta Imediata:").grid(row=3, column=0, padx=15, pady=10, sticky="e")
        self.entry_conduta = ctk.CTkEntry(form, width=640, placeholder_text="Ex: Lote segregado.")
        self.entry_conduta.grid(row=3, column=1, columnspan=3, padx=15, pady=10, sticky="w")

        btn_salvar = ctk.CTkButton(self.frame, text="💾 Registrar Evento Sanitário", fg_color="#c0392b",
                                   hover_color="#a33126", command=self.salvar_registro)
        btn_salvar.pack(pady=10, anchor="w", padx=5)

        self.tabela_frame = ctk.CTkFrame(self.frame)
        self.tabela_frame.pack(fill="both", expand=True, pady=10)

        self.tabela = ttk.Treeview(self.tabela_frame,
                                   columns=("ID", "Item/Lote", "Tipo", "Gravidade", "Data", "Operador"),
                                   show="headings")
        for col in self.tabela["columns"]: self.tabela.heading(col, text=col); self.tabela.column(col, anchor="center")
        self.tabela.pack(fill="both", expand=True, padx=10, pady=10)
        self.atualizar_tabela()

    def salvar_registro(self):
        if not self.entry_lote.get().strip() or not self.txt_desc.get().strip():
            messagebox.showwarning("Validação", "Preencha a descrição e o identificador do lote.")
            return

        db = conectar_bd()
        c = db.cursor()
        c.execute("""
            INSERT INTO tecnovigilancia (lote_texto, tipo_ocorrencia, descricao, gravidade, conduta, data_registro, operador)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (self.entry_lote.get().strip(), self.cb_tipo.get(), self.txt_desc.get().strip(), self.cb_gravidade.get(),
              self.entry_conduta.get().strip(), datetime.now().strftime("%Y-%m-%d %H:%M"), self.operador))
        db.commit()
        db.close()
        messagebox.showinfo("Sucesso", "Notificação interna salva com sucesso.")
        self.entry_lote.delete(0, 'end')
        self.txt_desc.delete(0, 'end')
        self.entry_conduta.delete(0, 'end')
        self.atualizar_tabela()

    def atualizar_tabela(self):
        for item in self.tabela.get_children(): self.tabela.delete(item)
        db = conectar_bd()
        c = db.cursor()
        for row in c.execute(
                "SELECT id, lote_texto, tipo_ocorrencia, gravidade, data_registro, operador FROM tecnovigilancia").fetchall():
            self.tabela.insert('', 'end', values=row)
        db.close()


# =========================================================================
# 3. DASHBOARD E MÓDULOS CORE DO SISTEMA HOSPITALAR
# =========================================================================
class SistemaHospitalar:
    def __init__(self, master, usuario, perfil):
        self.master = master
        self.usuario_logado = usuario
        self.perfil_logado = perfil

        self.master.title("SisFarma v.1 serie: 001 - Suporte - 91983252639")
        self.master.geometry("1340x800")

        self.med_id_selecionado = None
        self.med_dict = {}
        self.local_insumos_dict = {}
        self.lotes_dict = {}
        self.insumos_dict = {}
        self.inputs_dinamicos = {}

        self.ajustar_estilo_tabelas()

        # Header Superior
        header = ctk.CTkFrame(master=self.master, height=50, corner_radius=0, fg_color=("#1e3d59", "#112233"))
        header.pack(fill="x", side="top")

        ctk.CTkLabel(header, text="🏥 CENTRAL DE GESTÃO E DISPENSAÇÃO FARMACÊUTICA", font=("Segoe UI", 14, "bold"),
                     text_color="white").pack(side="left", padx=20, pady=10)
        ctk.CTkLabel(header, text=f"Operador: {self.usuario_logado} ({self.perfil_logado})",
                     font=("Segoe UI", 12, "italic"), text_color="#ecf0f1").pack(side="right", padx=20, pady=10)

        # Menu Lateral
        self.menu_lateral = ctk.CTkFrame(master=self.master, width=220, corner_radius=0)
        self.menu_lateral.pack(fill="y", side="left", padx=0, pady=0)

        # SEÇÃO MEDICAMENTOS
        ctk.CTkLabel(self.menu_lateral, text="MEDICAMENTOS", font=("Segoe UI", 11, "bold"), text_color="gray").pack(
            pady=(15, 2), padx=10, anchor="w")
        ctk.CTkButton(self.menu_lateral, text="💊 Catálogo Base", anchor="w", height=35,
                      command=self.tela_medicamentos).pack(fill="x", padx=10, pady=2)
        ctk.CTkButton(self.menu_lateral, text="📦 Entrada de Lotes", anchor="w", height=35,
                      command=self.tela_lotes).pack(fill="x", padx=10, pady=2)
        ctk.CTkButton(self.menu_lateral, text="⚡ Dispensar Itens", anchor="w", height=35,
                      command=self.tela_dispensacao).pack(fill="x", padx=10, pady=2)

        # SEÇÃO INSUMOS / MATERIAIS GERAIS
        ctk.CTkLabel(self.menu_lateral, text="INSUMOS / MATERIAIS", font=("Segoe UI", 11, "bold"),
                     text_color="gray").pack(pady=(15, 2), padx=10, anchor="w")
        ctk.CTkButton(self.menu_lateral, text="💉 Cadastro de Insumos", anchor="w", height=35, fg_color="#2c3e50",
                      hover_color="#34495e", command=self.tela_cadastro_insumos).pack(fill="x", padx=10, pady=2)
        ctk.CTkButton(self.menu_lateral, text="📥 Receber Insumos", anchor="w", height=35, fg_color="#2c3e50",
                      hover_color="#34495e", command=self.tela_lotes_insumos).pack(fill="x", padx=10, pady=2)

        # SEÇÃO SERVIÇOS DE ETIQUETAGEM
        ctk.CTkLabel(self.menu_lateral, text="SERVIÇOS DE IMPRESSÃO", font=("Segoe UI", 11, "bold"),
                     text_color="gray").pack(pady=(15, 2), padx=10, anchor="w")
        ctk.CTkButton(self.menu_lateral, text="🏷️ Gerador de Etiquetas", anchor="w", height=38, fg_color="#16a085",
                      hover_color="#117a65", command=self.tela_gerador_etiquetas).pack(fill="x", padx=10, pady=2)

        # SEÇÃO AUDITORIA E COMPLIANCE
        ctk.CTkLabel(self.menu_lateral, text="AUDITORIA", font=("Segoe UI", 11, "bold"), text_color="gray").pack(
            pady=(15, 2), padx=10, anchor="w")
        ctk.CTkButton(self.menu_lateral, text="🔍 Rastreabilidade", anchor="w", height=35,
                      command=self.tela_rastreabilidade).pack(fill="x", padx=10, pady=2)
        ctk.CTkButton(self.menu_lateral, text="⚠️ Alertas Clínicos", anchor="w", height=35,
                      command=self.tela_alertas_sanitarios).pack(fill="x", padx=10, pady=2)

        # RODAPÉ DO MENU
        self.btn_tecnovigilancia = ctk.CTkButton(self.menu_lateral, text="⚠️ Tecnovigilância (POP)", fg_color="#A30000",
                                                 hover_color="#7A0000", command=self.mostrar_tela_tecnovigilancia)
        self.btn_tecnovigilancia.pack(pady=(20, 5), padx=10, fill="x")

        self.btn_sobre = ctk.CTkButton(self.menu_lateral, text="ℹ️ Sobre o Sistema", fg_color="#34495e",
                                       hover_color="#2c3e50", command=self.mostrar_informacoes_software)
        self.btn_sobre.pack(pady=5, padx=10, fill="x")

        # Container Principal
        self.frame_conteudo = ctk.CTkScrollableFrame(master=self.master, corner_radius=15)
        self.frame_conteudo.pack(fill="both", expand=True, padx=20, pady=20)

        # Inicializa na tela de dispensação padrão de forma segura
        self.tela_dispensacao()

    def limpar_tela(self):
        for widget in self.frame_conteudo.winfo_children():
            widget.destroy()

    def ajustar_estilo_tabelas(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#ffffff", foreground="#222831", rowheight=30, fieldbackground="#ffffff",
                        font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#e9ecef", foreground="#222831", font=("Segoe UI", 10, "bold"),
                        bordercolor="#e9ecef", thickness=35)
        style.map("Treeview", background=[("selected", "#1f538d")], foreground=[("selected", "#ffffff")])

    def mostrar_tela_tecnovigilancia(self):
        self.limpar_tela()
        ModuloTecnovigilancia(self.frame_conteudo, self.usuario_logado)

    def mostrar_informacoes_software(self):
        sobre_janela = ctk.CTkToplevel(self.master)
        sobre_janela.title("Sobre o Sistema")
        sobre_janela.geometry("550x450")
        sobre_janela.resizable(False, False)
        sobre_janela.transient(self.master)
        sobre_janela.grab_set()

        frame_sobre = ctk.CTkFrame(sobre_janela, corner_radius=15)
        frame_sobre.pack(pady=15, padx=15, fill="both", expand=True)

        ctk.CTkLabel(frame_sobre, text="YANA v.1.0", font=("Segoe UI", 22, "bold"), text_color="#1f538d").pack(
            pady=(15, 2))

        caixa_texto = ctk.CTkTextbox(frame_sobre, width=480, height=180, font=("Segoe UI", 11))
        caixa_texto.pack(pady=5, padx=20, fill="x")
        caixa_texto.insert("1.0",
                           "Sistema em conformidade com RDC 430/2020 ANVISA para rastreabilidade de medicamentos e insumos correlatos em ambiente hospitalar público.")
        caixa_texto.configure(state="disabled")

        btn_fechar = ctk.CTkButton(frame_sobre, text="Fechar", width=160, command=sobre_janela.destroy)
        btn_fechar.pack(pady=15)

    # ---------------------------------------------------------------------
    # MÓDULO 1: MEDICAMENTOS
    # ---------------------------------------------------------------------
    def tela_medicamentos(self):
        self.limpar_tela()
        self.med_id_selecionado = None

        ctk.CTkLabel(self.frame_conteudo, text="Catálogo de Medicamentos Hospitalares",
                     font=("Segoe UI", 18, "bold")).pack(pady=10, anchor="w")

        form = ctk.CTkFrame(self.frame_conteudo)
        form.pack(fill="x", pady=10, padx=5)

        ctk.CTkLabel(form, text="Nome Comercial:").grid(row=0, column=0, padx=15, pady=10, sticky="e")
        self.ent_nome = ctk.CTkEntry(form, width=250)
        self.ent_nome.grid(row=0, column=1, padx=15, pady=10)

        ctk.CTkLabel(form, text="Princípio Ativo:").grid(row=0, column=2, padx=15, pady=10, sticky="e")
        self.ent_principio = ctk.CTkEntry(form, width=250)
        self.ent_principio.grid(row=0, column=3, padx=15, pady=10)

        ctk.CTkLabel(form, text="Categoria:").grid(row=1, column=0, padx=15, pady=10, sticky="e")
        self.ent_categoria = ctk.CTkComboBox(form, values=["Antimicrobiano", "Opioide", "Anestésico", "Psicotrópico",
                                                           "Injetável Comum", "Soros/Soluções"], width=250)
        self.ent_categoria.grid(row=1, column=1, padx=15, pady=10)

        ctk.CTkLabel(form, text="Código de Barras (EAN):").grid(row=1, column=2, padx=15, pady=10, sticky="e")
        self.ent_cod_barras = ctk.CTkEntry(form, width=250, placeholder_text="Aponte o leitor óptico...")
        self.ent_cod_barras.grid(row=1, column=3, padx=15, pady=10)

        self.controlado_var = ctk.StringVar(value="Não")
        self.check_ctrl = ctk.CTkCheckBox(form, text="Medicamento Controlado (Portaria 344)",
                                          variable=self.controlado_var, onvalue="Sim", offvalue="Não",
                                          text_color="#e74c3c")
        self.check_ctrl.grid(row=2, column=1, padx=15, pady=10, sticky="w")

        tabela_frame = ctk.CTkFrame(self.frame_conteudo)
        tabela_frame.pack(fill="both", expand=True, pady=10)

        self.tabela_meds = ttk.Treeview(tabela_frame, columns=(
        "ID", "Nome", "Princípio Ativo", "Categoria", "Código Barras", "Controlado"), show="headings")
        for col in self.tabela_meds["columns"]:
            self.tabela_meds.heading(col, text=col)
            self.tabela_meds.column(col, anchor="center")
        self.tabela_meds.pack(fill="both", expand=True, padx=10, pady=10)
        self.tabela_meds.bind("<<TreeviewSelect>>", self.carregar_dados_medicamento)

        actions = ctk.CTkFrame(self.frame_conteudo, fg_color="transparent")
        actions.pack(fill="x", pady=5)

        self.btn_salvar_med = ctk.CTkButton(actions, text="➕ Adicionar ao Catálogo", fg_color="#27ae60",
                                            hover_color="#218c53", command=self.salvar_medicamento)
        self.btn_salvar_med.pack(side="left", padx=5)

        self.atualizar_tabela_medicamentos()

    def carregar_dados_medicamento(self, event):
        item = self.tabela_meds.selection()
        if not item: return
        valores = self.tabela_meds.item(item)['values']
        self.med_id_selecionado = valores[0]

        self.ent_nome.delete(0, 'end')
        self.ent_nome.insert(0, valores[1])
        self.ent_principio.delete(0, 'end')
        self.ent_principio.insert(0, valores[2])
        self.ent_categoria.set(valores[3])
        self.ent_cod_barras.delete(0, 'end')
        self.ent_cod_barras.insert(0, valores[4] if valores[4] != "Nenhum" else "")

        if "⚠️" in str(valores[5]) or str(valores[5]).strip().lower() == "sim":
            self.check_ctrl.select()
            self.controlado_var.set("Sim")
        else:
            self.check_ctrl.deselect()
            self.controlado_var.set("Não")
        self.btn_salvar_med.configure(text="🔄 Atualizar Cadastro", fg_color="#d35400")

    def salvar_medicamento(self):
        nome = self.ent_nome.get().strip()
        principio = self.ent_principio.get().strip()
        categoria = self.ent_categoria.get()
        barras = self.ent_cod_barras.get().strip() if self.ent_cod_barras.get().strip() else "Nenhum"
        ctrl = 1 if self.controlado_var.get() == "Sim" else 0

        if not nome or not principio:
            messagebox.showwarning("Validação",
                                   "Campos estruturais obrigatórios (Nome Comercial e Princípio Ativo) em branco.")
            return

        db = conectar_bd()
        c = db.cursor()
        try:
            if self.med_id_selecionado is None:
                c.execute(
                    "INSERT INTO medicamentos (nome, principio_ativo, categoria, controlado, codigo_barras) VALUES (?,?,?,?,?)",
                    (nome, principio, categoria, ctrl, barras))
                messagebox.showinfo("Sucesso", f"Medicamento '{nome}' adicionado com sucesso!")
            else:
                c.execute(
                    "UPDATE medicamentos SET nome=?, principio_ativo=?, categoria=?, controlado=?, codigo_barras=? WHERE id=?",
                    (nome, principio, categoria, ctrl, barras, self.med_id_selecionado))
                messagebox.showinfo("Sucesso", "Cadastro atualizado com sucesso!")
            db.commit()
        except sqlite3.IntegrityError:
            messagebox.showerror("Erro de Chave", "Este Código de Barras já existe associado a outro registro.")
        except Exception as e:
            messagebox.showerror("Erro Crítico", f"Falha ao interagir com a base SQLite: {str(e)}")
        finally:
            db.close()

        self.tela_medicamentos()

    def atualizar_tabela_medicamentos(self):
        for item in self.tabela_meds.get_children():
            self.tabela_meds.delete(item)
        db = conectar_bd()
        c = db.cursor()
        c.execute(
            "SELECT id, nome, principio_ativo, categoria, codigo_barras, CASE WHEN controlado=1 THEN '⚠️ SIM' ELSE 'Não' END FROM medicamentos")
        for row in c.fetchall():
            self.tabela_meds.insert('', 'end', values=row)
        db.close()

    # ---------------------------------------------------------------------
    # MÓDULO: ENTRADA DE LOTES MEDICAMENTOS
    # ---------------------------------------------------------------------
    def tela_lotes(self):
        self.limpar_tela()

        ctk.CTkLabel(self.frame_conteudo, text="Recebimento e Inventário de Lotes (Medicamentos)",
                     font=("Segoe UI", 18, "bold")).pack(pady=10, anchor="w")

        form = ctk.CTkFrame(self.frame_conteudo)
        form.pack(fill="x", pady=10, padx=5)

        db = conectar_bd()
        c = db.cursor()
        self.med_dict = {f"{r[1]} ({r[2]})": r[0] for r in
                         c.execute("SELECT id, nome, principio_ativo FROM medicamentos").fetchall()}
        db.close()

        ctk.CTkLabel(form, text="Medicamento:").grid(row=0, column=0, padx=15, pady=10, sticky="e")
        self.cb_med = ctk.CTkComboBox(form,
                                      values=list(self.med_dict.keys()) if self.med_dict else ["Nenhum cadastrado"],
                                      width=250)
        self.cb_med.grid(row=0, column=1, padx=15, pady=10)

        ctk.CTkLabel(form, text="Lote (ANVISA):").grid(row=0, column=2, padx=15, pady=10, sticky="e")
        self.lote_num = ctk.CTkEntry(form, width=250)
        self.lote_num.grid(row=0, column=3, padx=15, pady=10)

        ctk.CTkLabel(form, text="Fabricante:").grid(row=1, column=0, padx=15, pady=10, sticky="e")
        self.fabricante = ctk.CTkEntry(form, width=250)
        self.fabricante.grid(row=1, column=1, padx=15, pady=10)

        ctk.CTkLabel(form, text="Fab. (AAAA-MM-DD):").grid(row=1, column=2, padx=15, pady=10, sticky="e")
        self.dt_fab = ctk.CTkEntry(form, width=250)
        self.dt_fab.grid(row=1, column=3, padx=15, pady=10)

        ctk.CTkLabel(form, text="Val. (AAAA-MM-DD):").grid(row=2, column=0, padx=15, pady=10, sticky="e")
        self.dt_val = ctk.CTkEntry(form, width=250)
        self.dt_val.grid(row=2, column=1, padx=15, pady=10)

        ctk.CTkLabel(form, text="Qtd Recebida:").grid(row=2, column=2, padx=15, pady=10, sticky="e")
        self.qtd = ctk.CTkEntry(form, width=250)
        self.qtd.grid(row=2, column=3, padx=15, pady=10)

        tabela_frame = ctk.CTkFrame(self.frame_conteudo)
        tabela_frame.pack(fill="both", expand=True, pady=10)

        tabela = ttk.Treeview(tabela_frame, columns=("ID", "Medicamento", "Lote", "Fabricante", "Validade", "Estoque"),
                              show="headings")
        for col in tabela["columns"]: tabela.heading(col, text=col); tabela.column(col, anchor="center")
        tabela.pack(fill="both", expand=True, padx=10, pady=10)

        btn_salvar = ctk.CTkButton(self.frame_conteudo, text="➕ Dar Entrada de Lote", fg_color="#27ae60",
                                   command=self.salvar_lote)
        btn_salvar.pack(pady=5, anchor="w", padx=5)

        db = conectar_bd()
        c = db.cursor()
        c.execute(
            "SELECT l.id, med.nome, l.numero_lote, l.fabricante, l.validade, l.quantidade FROM lotes l JOIN medicamentos med ON l.medicamento_id = med.id")
        for row in c.fetchall(): tabela.insert('', 'end', values=row)
        db.close()

    def salvar_lote(self):
        if not self.cb_med.get() or self.cb_med.get() not in self.med_dict:
            messagebox.showerror("Erro de Validação", "Selecione um medicamento válido da lista.")
            return
        try:
            datetime.strptime(self.dt_fab.get().strip(), "%Y-%m-%d")
            datetime.strptime(self.dt_val.get().strip(), "%Y-%m-%d")
            q = int(self.qtd.get().strip())
            if q <= 0: raise ValueError
        except ValueError:
            messagebox.showerror("Erro",
                                 "Inconformidade nas datas (Formato correto: AAAA-MM-DD) ou quantidades numéricas inválidas.")
            return

        db = conectar_bd()
        c = db.cursor()
        try:
            c.execute(
                "INSERT INTO lotes (medicamento_id, numero_lote, fabricante, data_fabricacao, validade, quantidade) VALUES (?,?,?,?,?,?)",
                (self.med_dict[self.cb_med.get()], self.lote_num.get().strip(), self.fabricante.get().strip(),
                 self.dt_fab.get().strip(), self.dt_val.get().strip(), q))
            db.commit()
        except Exception as e:
            messagebox.showerror("Erro de Escrita", f"Não foi possível salvar o lote: {str(e)}")
        finally:
            db.close()
        self.tela_lotes()

    # ---------------------------------------------------------------------
    # MÓDULO 2: GESTÃO DE INSUMOS GERAIS
    # ---------------------------------------------------------------------
    def tela_cadastro_insumos(self):
        self.limpar_tela()

        ctk.CTkLabel(self.frame_conteudo, text="Catálogo Geral de Insumos & Materiais Correlatos",
                     font=("Segoe UI", 18, "bold")).pack(pady=10, anchor="w")
        form = ctk.CTkFrame(self.frame_conteudo)
        form.pack(fill="x", pady=10, padx=5)

        ctk.CTkLabel(form, text="Nome do Insumo:").grid(row=0, column=0, padx=15, pady=10, sticky="e")
        self.ins_nome = ctk.CTkEntry(form, width=250)
        self.ins_nome.grid(row=0, column=1, padx=15, pady=10)

        ctk.CTkLabel(form, text="Especificação Técnica:").grid(row=0, column=2, padx=15, pady=10, sticky="e")
        self.ins_espec = ctk.CTkEntry(form, width=250)
        self.ins_espec.grid(row=0, column=3, padx=15, pady=10)

        ctk.CTkLabel(form, text="Unidade de Medida:").grid(row=1, column=0, padx=15, pady=10, sticky="e")
        self.ins_unidade = ctk.CTkComboBox(form, values=["Unidade", "Frasco", "Caixa", "Pacote", "Rolo"], width=250)
        self.ins_unidade.grid(row=1, column=1, padx=15, pady=10)

        ctk.CTkLabel(form, text="Grupo/Classe:").grid(row=1, column=2, padx=15, pady=10, sticky="e")
        self.ins_grupo = ctk.CTkComboBox(form, values=["Correlatos/Descartáveis", "EPIs", "Acessórios de Infusão",
                                                       "Higienização"], width=250)
        self.ins_grupo.grid(row=1, column=3, padx=15, pady=10)

        tabela_frame = ctk.CTkFrame(self.frame_conteudo)
        tabela_frame.pack(fill="both", expand=True, pady=10)

        tabela = ttk.Treeview(tabela_frame, columns=("ID", "Nome", "Especificação", "Unidade", "Grupo"),
                              show="headings")
        for col in tabela["columns"]: tabela.heading(col, text=col); tabela.column(col, anchor="center")
        tabela.pack(fill="both", expand=True, padx=10, pady=10)

        btn_salvar = ctk.CTkButton(self.frame_conteudo, text="➕ Cadastrar Insumo", fg_color="#27ae60",
                                   command=self.salvar_insumo)
        btn_salvar.pack(pady=5, anchor="w", padx=5)

        db = conectar_bd()
        c = db.cursor()
        for row in c.execute("SELECT * FROM insumos").fetchall(): tabela.insert('', 'end', values=row)
        db.close()

    def salvar_insumo(self):
        nome = self.ins_nome.get().strip()
        if not nome:
            messagebox.showwarning("Aviso", "O nome do insumo é obrigatório.")
            return
        db = conectar_bd()
        c = db.cursor()
        c.execute("INSERT INTO insumos (nome, especificacao, unidade_medida, grupo) VALUES (?, ?, ?, ?)",
                  (nome, self.ins_espec.get().strip(), self.ins_unidade.get(), self.ins_grupo.get()))
        db.commit()
        db.close()
        self.tela_cadastro_insumos()

    def tela_lotes_insumos(self):
        self.limpar_tela()
        ctk.CTkLabel(self.frame_conteudo, text="Recebimento e Inventário de Lotes (Insumos/Materiais)",
                     font=("Segoe UI", 18, "bold")).pack(pady=10, anchor="w")

        form = ctk.CTkFrame(self.frame_conteudo)
        form.pack(fill="x", pady=10, padx=5)

        db = conectar_bd()
        c = db.cursor()
        self.local_insumos_dict = {f"{r[1]} - {r[2]}": r[0] for r in
                                   c.execute("SELECT id, nome, especificacao FROM insumos").fetchall()}
        db.close()

        ctk.CTkLabel(form, text="Insumo Base:").grid(row=0, column=0, padx=15, pady=10, sticky="e")
        self.cb_insumo = ctk.CTkComboBox(form,
                                         values=list(self.local_insumos_dict.keys()) if self.local_insumos_dict else [
                                             "Nenhum cadastrado"], width=250)
        self.cb_insumo.grid(row=0, column=1, padx=15, pady=10)

        ctk.CTkLabel(form, text="Número do Lote:").grid(row=0, column=2, padx=15, pady=10, sticky="e")
        self.ins_lote_num = ctk.CTkEntry(form, width=250)
        self.ins_lote_num.grid(row=0, column=3, padx=15, pady=10)

        ctk.CTkLabel(form, text="Fabricante:").grid(row=1, column=0, padx=15, pady=10, sticky="e")
        self.ins_fabricante = ctk.CTkEntry(form, width=250)
        self.ins_fabricante.grid(row=1, column=1, padx=15, pady=10)

        ctk.CTkLabel(form, text="Validade (AAAA-MM-DD):").grid(row=1, column=2, padx=15, pady=10, sticky="e")
        self.ins_validade = ctk.CTkEntry(form, width=250)
        self.ins_validade.grid(row=1, column=3, padx=15, pady=10)

        ctk.CTkLabel(form, text="Quantidade:").grid(row=2, column=0, padx=15, pady=10, sticky="e")
        self.ins_quantidade = ctk.CTkEntry(form, width=250)
        self.ins_quantidade.grid(row=2, column=1, padx=15, pady=10)

        tabela_frame = ctk.CTkFrame(self.frame_conteudo)
        tabela_frame.pack(fill="both", expand=True, pady=10)

        tabela = ttk.Treeview(tabela_frame, columns=("ID", "Insumo", "Lote", "Fabricante", "Validade", "Quantidade"),
                              show="headings")
        for col in tabela["columns"]: tabela.heading(col, text=col); tabela.column(col, anchor="center")
        tabela.pack(fill="both", expand=True, padx=10, pady=10)

        btn_salvar = ctk.CTkButton(self.frame_conteudo, text="📥 Dar Entrada de Insumo", fg_color="#27ae60",
                                   command=self.salvar_lote_insumo)
        btn_salvar.pack(pady=5, anchor="w", padx=5)

        db = conectar_bd()
        c = db.cursor()
        c.execute(
            "SELECT li.id, i.nome, li.numero_lote, li.fabricante, li.validade, li.quantidade FROM lotes_insumos li JOIN insumos i ON li.insumo_id = i.id")
        for row in c.fetchall(): tabela.insert('', 'end', values=row)
        db.close()

    def salvar_lote_insumo(self):
        if not self.cb_insumo.get() or self.cb_insumo.get() not in self.local_insumos_dict:
            messagebox.showerror("Erro", "Selecione um insumo básico do catálogo.")
            return
        try:
            datetime.strptime(self.ins_validade.get().strip(), "%Y-%m-%d")
            q = int(self.ins_quantidade.get().strip())
            if q <= 0: raise ValueError
        except ValueError:
            messagebox.showerror("Erro de Validação",
                                 "Insira uma data válida (AAAA-MM-DD) e quantidade maior que zero.")
            return

        db = conectar_bd()
        c = db.cursor()
        c.execute("""
            INSERT INTO lotes_insumos (insumo_id, numero_lote, fabricante, validade, quantidade)
            VALUES (?, ?, ?, ?, ?)
        """, (self.local_insumos_dict[self.cb_insumo.get()], self.ins_lote_num.get().strip(),
              self.ins_fabricante.get().strip(), self.ins_validade.get().strip(), q))
        db.commit()
        db.close()
        self.tela_lotes_insumos()

    # ---------------------------------------------------------------------
    # MÓDULO 3: DISPENSAÇÃO / SAÍDA UNIFICADA
    # ---------------------------------------------------------------------
    def tela_dispensacao(self):
        self.limpar_tela()

        ctk.CTkLabel(self.frame_conteudo, text="Painel Unificado de Dispensação e Baixa de Materiais",
                     font=("Segoe UI", 18, "bold")).pack(pady=10, anchor="w")

        tipo_frame = ctk.CTkFrame(self.frame_conteudo, fg_color="transparent")
        tipo_frame.pack(fill="x", pady=5, padx=5)

        ctk.CTkLabel(tipo_frame, text="Tipo de Material a Dispensar:", font=("Segoe UI", 12, "bold")).pack(side="left",
                                                                                                           padx=5)
        self.radio_var = ctk.StringVar(value="MEDICAMENTO")

        rb_med = ctk.CTkRadioButton(tipo_frame, text="Medicamento", variable=self.radio_var, value="MEDICAMENTO",
                                    command=self.sincronizar_combobox_dispensacao)
        rb_med.pack(side="left", padx=15)

        rb_ins = ctk.CTkRadioButton(tipo_frame, text="Insumo Geral / Correlato", variable=self.radio_var,
                                    value="INSUMO", command=self.sincronizar_combobox_dispensacao)
        rb_ins.pack(side="left", padx=15)

        form = ctk.CTkFrame(self.frame_conteudo)
        form.pack(fill="x", pady=10, padx=5)

        ctk.CTkLabel(form, text="Selecionar Lote/Item:").grid(row=0, column=0, padx=15, pady=10, sticky="e")
        self.cb_lotes = ctk.CTkComboBox(form, values=[], width=450)
        self.cb_lotes.grid(row=0, column=1, columnspan=2, padx=15, pady=10, sticky="w")

        ctk.CTkLabel(form, text="Paciente / Destino:").grid(row=1, column=0, padx=15, pady=10, sticky="e")
        self.disp_paciente = ctk.CTkEntry(form, width=300, placeholder_text="Nome do Paciente ou Uso Geral")
        self.disp_paciente.grid(row=1, column=1, padx=15, pady=10, sticky="w")

        ctk.CTkLabel(form, text="Nº Prescrição / Req:").grid(row=1, column=2, padx=15, pady=10, sticky="e")
        self.disp_prescricao = ctk.CTkEntry(form, width=200, placeholder_text="Nº Controle")
        self.disp_prescricao.grid(row=1, column=3, padx=15, pady=10, sticky="w")

        ctk.CTkLabel(form, text="Setor Requisitante:").grid(row=2, column=0, padx=15, pady=10, sticky="e")
        self.disp_setor = ctk.CTkComboBox(form, values=["Clínica Médica", "UTI Adulto", "Pediatria", "Centro Cirúrgico",
                                                        "Pronto Socorro", "Almoxarifado Central"], width=300)
        self.disp_setor.grid(row=2, column=1, padx=15, pady=10, sticky="w")

        ctk.CTkLabel(form, text="Qtd Solicitada:").grid(row=2, column=2, padx=15, pady=10, sticky="e")
        self.disp_qtd = ctk.CTkEntry(form, width=200)
        self.disp_qtd.grid(row=2, column=3, padx=15, pady=10, sticky="w")

        self.sincronizar_combobox_dispensacao()

        btn_processar = ctk.CTkButton(self.frame_conteudo, text="⚡ Processar Dispensação", fg_color="#e67e22",
                                      font=("Segoe UI", 13, "bold"), command=self.registrar_dispensacao)
        btn_processar.pack(pady=10, anchor="w", padx=5)

        tabela_frame = ctk.CTkFrame(self.frame_conteudo)
        tabela_frame.pack(fill="both", expand=True, pady=10)

        ctk.CTkLabel(tabela_frame, text="Últimas Movimentações Sincronizadas (Tempo Real)",
                     font=("Segoe UI", 12, "bold"), text_color="gray").pack(anchor="w", padx=10, pady=5)

        tabela = ttk.Treeview(tabela_frame, columns=("ID", "Tipo", "Qtd", "Destino", "Paciente/Fins", "Data/Hora"),
                              show="headings")
        for col in tabela["columns"]: tabela.heading(col, text=col); tabela.column(col, anchor="center")
        tabela.pack(fill="both", expand=True, padx=10, pady=10)

        db = conectar_bd()
        c = db.cursor()
        movs = c.execute("""
            SELECT id, tipo, quantidade, setor_destino, paciente_nome, data_movimentacao
            FROM movimentacoes ORDER BY id DESC LIMIT 10
        """).fetchall()
        db.close()
        for r in movs: tabela.insert('', 'end', values=r)

    def registrar_dispensacao(self):
        escolha = self.cb_lotes.get()
        modo = self.radio_var.get()

        if modo == "MEDICAMENTO":
            if not escolha or escolha not in self.lotes_dict:
                messagebox.showerror("Erro", "Selecione um lote de medicamento válido.")
                return
            lote_id, atual_qtd = self.lotes_dict[escolha]
        else:
            if not escolha or escolha not in self.insumos_dict:
                messagebox.showerror("Erro", "Selecione um lote de insumo válido.")
                return
            lote_id, atual_qtd = self.insumos_dict[escolha]

        try:
            baixa = int(self.disp_qtd.get().strip())
            if baixa <= 0 or baixa > atual_qtd: raise ValueError
        except ValueError:
            messagebox.showerror("Inconsistência", f"Quantidade inválida. Saldo em estoque: {atual_qtd}")
            return

        db = conectar_bd()
        c = db.cursor()

        if modo == "MEDICAMENTO":
            c.execute("UPDATE lotes SET quantidade = quantidade - ? WHERE id = ?", (baixa, lote_id))
            c.execute("""
                INSERT INTO movimentacoes (lote_id, insumo_lote_id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao)
                VALUES (?, NULL, 'SAÍDA MEDICAMENTO', ?, ?, ?, ?, ?, ?)
            """, (
            lote_id, baixa, self.disp_setor.get(), self.disp_paciente.get().strip(), self.disp_prescricao.get().strip(),
            self.usuario_logado, datetime.now().strftime("%Y-%m-%d %H:%M")))
        else:
            c.execute("UPDATE lotes_insumos SET quantidade = quantidade - ? WHERE id = ?", (baixa, lote_id))
            c.execute("""
                INSERT INTO movimentacoes (lote_id, insumo_lote_id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao)
                VALUES (NULL, ?, 'SAÍDA INSUMO', ?, ?, ?, ?, ?, ?)
            """, (
            lote_id, baixa, self.disp_setor.get(), self.disp_paciente.get().strip(), self.disp_prescricao.get().strip(),
            self.usuario_logado, datetime.now().strftime("%Y-%m-%d %H:%M")))

        db.commit()
        db.close()

        messagebox.showinfo("Sucesso", "Baixa sincronizada no estoque com absoluto sucesso.")
        self.tela_dispensacao()

    def sincronizar_combobox_dispensacao(self):
        db = conectar_bd()
        c = db.cursor()
        modo = self.radio_var.get()

        if modo == "MEDICAMENTO":
            lotes_raw = c.execute("""
                SELECT l.id, m.nome, m.principio_ativo, l.numero_lote, l.quantidade
                FROM lotes l JOIN medicamentos m ON l.medicamento_id = m.id WHERE l.quantidade > 0
            """).fetchall()
            self.lotes_dict = {f"💊 {r[1]} ({r[2]}) - Lote: {r[3]} [Qtd: {r[4]}]": (r[0], r[4]) for r in lotes_raw}
            self.cb_lotes.configure(values=list(self.lotes_dict.keys()))
            if self.lotes_dict:
                self.cb_lotes.set(list(self.lotes_dict.keys())[0])
            else:
                self.cb_lotes.set("NENHUM MEDICAMENTO EM ESTOQUE")
        else:
            insumos_raw = c.execute("""
                SELECT li.id, i.nome, i.especificacao, li.numero_lote, li.quantidade
                FROM lotes_insumos li JOIN insumos i ON li.insumo_id = i.id WHERE li.quantidade > 0
            """).fetchall()
            self.insumos_dict = {f"💉 {r[1]} ({r[2]}) - Lote: {r[3]} [Qtd: {r[4]}]": (r[0], r[4]) for r in insumos_raw}
            self.cb_lotes.configure(values=list(self.insumos_dict.keys()))
            if self.insumos_dict:
                self.cb_lotes.set(list(self.insumos_dict.keys())[0])
            else:
                self.cb_lotes.set("NENHUM INSUMO EM ESTOQUE")
        db.close()

    # ---------------------------------------------------------------------
    # MÓDULO 4: SERVIÇOS DE ETIQUETAGEM E IMPRESSÃO
    # ---------------------------------------------------------------------
    def tela_gerador_etiquetas(self):
        self.limpar_tela()

        ctk.CTkLabel(self.frame_conteudo, text="🏷️ Gerador e Pré-visualizador de Etiquetas",
                     font=("Segoe UI", 18, "bold")).pack(pady=10, anchor="w")

        self.grid_etiquetas = ctk.CTkFrame(self.frame_conteudo, fg_color="transparent")
        self.grid_etiquetas.pack(fill="both", expand=True, pady=10)

        self.grid_etiquetas.grid_columnconfigure(0, weight=1)
        self.grid_etiquetas.grid_columnconfigure(1, weight=3)

        painel_esquerdo = ctk.CTkFrame(self.grid_etiquetas, fg_color=("#f8f9fa", "#1a1c23"), corner_radius=10)
        painel_esquerdo.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.painel_grade = ctk.CTkScrollableFrame(self.grid_etiquetas, fg_color="#ffffff", corner_radius=10)
        self.painel_grade.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        ctk.CTkLabel(painel_esquerdo, text="CONFIGURAÇÃO", font=("Segoe UI", 12, "bold"), text_color="#1f538d").pack(
            anchor="w", padx=15, pady=(15, 2))

        self.combo_tipo = ctk.CTkComboBox(painel_esquerdo,
                                          values=["1. Paciente / Leito", "2. Líquidos / Fracionados", "3. Comprimidos"],
                                          command=self.alternar_campos_etiqueta, height=35)
        self.combo_tipo.pack(fill="x", padx=15, pady=(0, 15))

        self.container_inputs = ctk.CTkFrame(painel_esquerdo, fg_color="transparent")
        self.container_inputs.pack(fill="x", padx=15, pady=0)

        ctk.CTkLabel(painel_esquerdo, text="Quantidade de Linhas:", font=("Segoe UI", 11)).pack(anchor="w", padx=15,
                                                                                                pady=(10, 2))
        self.entry_linhas = ctk.CTkEntry(painel_esquerdo, width=80, height=30)
        self.entry_linhas.insert(0, "4")
        self.entry_linhas.pack(anchor="w", padx=15, pady=0)

        self.btn_gerar = ctk.CTkButton(painel_esquerdo, text="Gerar Grade", fg_color="#118ab2",
                                       font=("Segoe UI", 13, "bold"), height=40, command=self.processar_e_gerar_grade)
        self.btn_gerar.pack(fill="x", padx=15, pady=20)

        self.combo_tipo.set("1. Paciente / Leito")
        self.alternar_campos_etiqueta("1. Paciente / Leito")

    def alternar_campos_etiqueta(self, tipo):
        for widget in self.container_inputs.winfo_children(): widget.destroy()
        self.inputs_dinamicos = {}

        if "1. Paciente / Leito" in tipo:
            campos = [
                ("Paciente", "NOME DO PACIENTE"),
                ("Data Nasc.", "__/__/____"),
                ("Leito", "EX: 04"),
                ("Atendimento", "Nº Atend."),
                ("Medicamento", "USO ESPECÍFICO"),
                ("Lote", "Lote med."),
                ("Data Disp.", datetime.now().strftime("%d/%m/%Y"))
            ]
        elif "2. Líquidos / Fracionados" in tipo:
            campos = [
                ("Medicamento", "AMBROXOL"),
                ("Concentração", "30MG/ML"),
                ("Qtd / Volume", "5 ML"),
                ("Lote", "LOT2411"),
                ("Val. Pós-Abertura", "15 DIAS")
            ]
        else:
            campos = [
                ("Nome do Comprimido", "Captopril"),
                ("Dosagem", "25mg"),
                ("Validade (V:)", "04/2027"),
                ("Lote (L:)", "2508916")
            ]

        for label_text, placeholder in campos:
            lbl = ctk.CTkLabel(self.container_inputs, text=label_text, font=("Segoe UI", 11), text_color="gray")
            lbl.pack(anchor="w", pady=(3, 0))
            ent = ctk.CTkEntry(self.container_inputs, placeholder_text=placeholder, height=30)
            ent.pack(fill="x", pady=(0, 3))
            self.inputs_dinamicos[label_text] = ent

    def processar_e_gerar_grade(self):
        for widget in self.painel_grade.winfo_children(): widget.destroy()
        tipo_ativo = self.combo_tipo.get()
        try:
            linhas = int(self.entry_linhas.get())
        except ValueError:
            linhas = 4

        if "1. Paciente / Leito" in tipo_ativo:
            self.renderizar_grade_paciente(linhas)
        elif "2. Líquidos / Fracionados" in tipo_ativo:
            self.renderizar_grade_liquidos(linhas)
        else:
            self.renderizar_grade_comprimidos(linhas)

    def renderizar_grade_paciente(self, rows):
        paciente = self.inputs_dinamicos["Paciente"].get() or "NOME DO PACIENTE"
        nasc = self.inputs_dinamicos["Data Nasc."].get() or "__/__/____"
        leito = self.inputs_dinamicos["Leito"].get() or "____"
        atend = self.inputs_dinamicos["Atendimento"].get() or "_______"
        med = self.inputs_dinamicos["Medicamento"].get() or "USO ESPECÍFICO"
        lote = self.inputs_dinamicos["Lote"].get() or "________"
        data_d = self.inputs_dinamicos["Data Disp."].get() or datetime.now().strftime("%d/%m/%Y")

        for r in range(rows):
            for c in range(3):
                box = tk.Frame(self.painel_grade, bg="white", highlightbackground="black", highlightthickness=1)
                box.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")

                tk.Label(box, text=f"Leito: {leito}", bg="white", fg="black", font=("Arial", 9, "bold")).pack(
                    anchor="w", padx=5, pady=(2, 0))
                tk.Label(box, text=f"Data: {data_d}", bg="white", fg="black", font=("Arial", 8, "bold")).pack(
                    anchor="w", padx=5)
                canvas_linha = tk.Frame(box, height=1, bg="black");
                canvas_linha.pack(fill="x", padx=5, pady=2)

                tk.Label(box, text=f"Paciente: {paciente.upper()}", bg="white", fg="black",
                         font=("Arial", 9, "bold")).pack(anchor="w", padx=5)
                tk.Label(box, text=f"Data de Nasc.: {nasc}", bg="white", fg="black", font=("Arial", 8)).pack(anchor="w",
                                                                                                             padx=5)
                tk.Label(box, text=f"Medicamento: {med}", bg="white", fg="black", font=("Arial", 8)).pack(anchor="w",
                                                                                                          padx=5)
                canvas_linha2 = tk.Frame(box, height=1, bg="gray");
                canvas_linha2.pack(fill="x", padx=5, pady=2)

                tk.Label(box, text=f"Lote: {lote}", bg="white", fg="black", font=("Arial", 8)).pack(anchor="w", padx=5)
                tk.Label(box, text=f"Atendimento: {atend}", bg="white", fg="black", font=("Arial", 8)).pack(anchor="w",
                                                                                                            padx=5)
                tk.Label(box, text=f"Leito: {leito}", bg="white", fg="black", font=("Arial", 8)).pack(anchor="w",
                                                                                                      padx=5)
                tk.Label(box, text=f"Data: {data_d}", bg="white", fg="black", font=("Arial", 8, "bold")).pack(
                    anchor="w", padx=5, pady=(0, 4))

    def renderizar_grade_liquidos(self, rows):
        med = self.inputs_dinamicos["Medicamento"].get() or "AMBROXOL"
        conc = self.inputs_dinamicos["Concentração"].get() or "30MG/ML"
        vol = self.inputs_dinamicos["Qtd / Volume"].get() or "5 ML"
        lote = self.inputs_dinamicos["Lote"].get() or "LOT2411"
        vpa = self.inputs_dinamicos["Val. Pós-Abertura"].get() or "15 DIAS"

        for r in range(rows):
            for c in range(6):
                box = tk.Frame(self.painel_grade, bg="white", highlightbackground="black", highlightthickness=1,
                               width=130, height=90)
                box.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")
                box.pack_propagate(False)

                tk.Label(box, text=med.upper(), bg="white", fg="black", font=("Arial", 9, "bold")).pack(anchor="w",
                                                                                                        padx=4,
                                                                                                        pady=(4, 0))
                tk.Label(box, text=conc.upper(), bg="white", fg="gray", font=("Arial", 8)).pack(anchor="w", padx=4)

                lbl_vol = tk.Label(box, text=vol, bg="white", fg="#0077b6", font=("Arial", 9, "bold"))
                lbl_vol.pack(anchor="w", padx=4, pady=2)

                tk.Label(box, text=f"L: {lote}", bg="white", fg="black", font=("Arial", 7)).pack(anchor="w", padx=4)
                tk.Label(box, text=f"V.P.A: {vpa}", bg="white", fg="#e63946", font=("Arial", 7, "bold")).pack(
                    anchor="w", padx=4, pady=(0, 4))

    def renderizar_grade_comprimidos(self, rows):
        nome = self.inputs_dinamicos["Nome do Comprimido"].get() or "Captopril"
        dosagem = self.inputs_dinamicos["Dosagem"].get() or "25mg"
        val = self.inputs_dinamicos["Validade (V:)"].get() or "04/2027"
        lote = self.inputs_dinamicos["Lote (L:)"].get() or "2508916"

        for r in range(rows):
            for c in range(8):
                box = tk.Frame(self.painel_grade, bg="white", highlightbackground="black", highlightthickness=1,
                               width=95, height=60)
                box.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
                box.pack_propagate(False)

                tk.Label(box, text="P.A.", bg="white", fg="gray", font=("Arial", 6)).pack(anchor="w", padx=3,
                                                                                          pady=(2, 0))
                tk.Label(box, text=f"{nome} {dosagem}", bg="white", fg="black", font=("Arial", 8, "bold")).pack(
                    anchor="w", padx=3)
                tk.Label(box, text=f"V: {val}", bg="white", fg="black", font=("Arial", 7)).pack(anchor="w", padx=3)
                tk.Label(box, text=f"L: {lote}", bg="white", fg="black", font=("Arial", 7)).pack(anchor="w", padx=3,
                                                                                                 pady=(0, 2))

    # ---------------------------------------------------------------------
    # MÓDULO 5: AUDITORIA E COMPLIANCE
    # ---------------------------------------------------------------------
    def tela_rastreabilidade(self):
        self.limpar_tela()
        ctk.CTkLabel(self.frame_conteudo, text="Rastreabilidade Extensa (RDC 430/2020)",
                     font=("Segoe UI", 18, "bold")).pack(pady=10, anchor="w")

        tabela_frame = ctk.CTkFrame(self.frame_conteudo)
        tabela_frame.pack(fill="both", expand=True, pady=10)

        tabela = ttk.Treeview(tabela_frame, columns=(
        "ID", "Tipo Operação", "Qtd", "Setor Destino", "Paciente / Fins", "Nº Doc/Prescrição", "Responsável",
        "Data/Hora Sinc."), show="headings")
        for col in tabela["columns"]: tabela.heading(col, text=col); tabela.column(col, anchor="center")
        tabela.pack(fill="both", expand=True, padx=10, pady=10)

        db = conectar_bd()
        c = db.cursor()
        for row in c.execute(
                "SELECT id, tipo, quantidade, setor_destino, paciente_nome, prescricao_num, responsavel, data_movimentacao FROM movimentacoes ORDER BY id DESC").fetchall():
            tabela.insert('', 'end', values=row)
        db.close()

    def tela_alertas_sanitarios(self):
        self.limpar_tela()
        ctk.CTkLabel(self.frame_conteudo, text="Alertas Clínicos & Validação Sanitária Crítica",
                     font=("Segoe UI", 18, "bold"), text_color="#e74c3c").pack(pady=10, anchor="w")

        box_alerta = ctk.CTkFrame(self.frame_conteudo, fg_color=("#fdedec", "#2c1a1a"), border_color="#e74c3c",
                                  border_width=1)
        box_alerta.pack(fill="x", pady=10, padx=5)

        data_atual_str = datetime.now().strftime("%Y-%m-%d")

        db = conectar_bd()
        c = db.cursor()
        lotes_med = c.execute(
            "SELECT m.nome, l.numero_lote, l.validade, l.quantidade FROM lotes l JOIN medicamentos m ON l.medicamento_id = m.id WHERE l.quantidade > 0").fetchall()
        lotes_ins = c.execute(
            "SELECT i.nome, li.numero_lote, li.validade, li.quantidade FROM lotes_insumos li JOIN insumos i ON li.insumo_id = i.id WHERE li.quantidade > 0").fetchall()
        db.close()

        vencidos_detectados = []

        for nome, lote, validade, qtd in lotes_med:
            if validade <= data_atual_str:
                vencidos_detectados.append(
                    f"💊 MEDICAMENTO: {nome} | Lote: {lote} | Vencimento: {validade} | Estoque: {qtd} un.")

        for nome, lote, validade, qtd in lotes_ins:
            if validade <= data_atual_str:
                vencidos_detectados.append(
                    f"💉 INSUMO: {nome} | Lote: {lote} | Vencimento: {validade} | Estoque: {qtd} un.")

        if vencidos_detectados:
            ctk.CTkLabel(box_alerta, text="⚠️ PRODUTOS VENCIDOS EM ESTOQUE (BLOQUEIO SANITÁRIO IMEDIATO)",
                         font=("Segoe UI", 13, "bold"), text_color="#c0392b").pack(anchor="w", padx=15, pady=10)
            for item in vencidos_detectados:
                ctk.CTkLabel(box_alerta, text=item, font=("Segoe UI", 12)).pack(anchor="w", padx=30, pady=2)
        else:
            ctk.CTkLabel(box_alerta, text="✅ Sistema Limpo: Nenhum lote de medicamento ou insumo fora da validade.",
                         font=("Segoe UI", 12, "bold"), text_color="#27ae60").pack(anchor="w", padx=15, pady=15)


# =========================================================================
# BLOCO DE EXECUÇÃO PRINCIPAL
# =========================================================================
if __name__ == "__main__":
    inicializar_banco()
    root_login = ctk.CTk()
    login_app = Login(root_login)
    root_login.mainloop()

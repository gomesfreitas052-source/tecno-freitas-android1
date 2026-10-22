import os
import sys
import json
import math
import sqlite3
from datetime import datetime

from kivy.app import App
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.image import Image
from kivy.uix.widget import Widget

NOME_APP = "TECNO FREITAS"
COR_VERDE = "#08C853"
COR_AZUL = "#2962FF"
COR_CINZA = "#202020"
COR_FUNDO = "#121212"
COR_BRANCO = "#FFFFFF"

Window.clearcolor = get_color_from_hex(COR_FUNDO)


def cor(valor):
    return get_color_from_hex(valor)


def dinheiro(valor):
    return "{:,.2f} Kz".format(float(valor)).replace(",", " ")


def data_atual():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


class BaseDados:
    def __init__(self, caminho):
        self.caminho = caminho
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        self.criar_tabelas()

    def ligar(self):
        db = sqlite3.connect(self.caminho, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def criar_tabelas(self):
        with self.ligar() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS vendas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT NOT NULL,
                    total REAL NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS itens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    venda_id INTEGER NOT NULL,
                    nome TEXT NOT NULL,
                    preco REAL NOT NULL,
                    quantidade INTEGER NOT NULL,
                    subtotal REAL NOT NULL,
                    FOREIGN KEY(venda_id) REFERENCES vendas(id)
                    ON DELETE CASCADE
                )
            """)

    def registar_venda(self, produtos):
        if not produtos:
            raise ValueError("A venda não tem produtos.")
        total = round(sum(p["subtotal"] for p in produtos), 2)
        with self.ligar() as db:
            cursor = db.execute(
                "INSERT INTO vendas (data, total) VALUES (?, ?)",
                (data_atual(), total)
            )
            venda_id = cursor.lastrowid
            for p in produtos:
                db.execute("""
                    INSERT INTO itens
                    (venda_id, nome, preco, quantidade, subtotal)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    venda_id, p["nome"], p["preco"],
                    p["quantidade"], p["subtotal"]
                ))
        return venda_id, total

    def listar_vendas(self):
        with self.ligar() as db:
            return db.execute("""
                SELECT id, data, total FROM vendas ORDER BY id DESC
            """).fetchall()

    def obter_venda(self, venda_id):
        with self.ligar() as db:
            venda = db.execute(
                "SELECT * FROM vendas WHERE id = ?", (venda_id,)
            ).fetchone()
            if venda is None:
                return None, []
            itens = db.execute("""
                SELECT nome, preco, quantidade, subtotal
                FROM itens WHERE venda_id = ? ORDER BY id
            """, (venda_id,)).fetchall()
            return venda, itens

    def resumo(self):
        with self.ligar() as db:
            r = db.execute("""
                SELECT COUNT(*) AS quantidade,
                       COALESCE(SUM(total), 0) AS total,
                       COALESCE(AVG(total), 0) AS media
                FROM vendas
            """).fetchone()
            return dict(r)

    def exportar_json(self):
        with self.ligar() as db:
            vendas = db.execute(
                "SELECT * FROM vendas ORDER BY id"
            ).fetchall()
            itens = db.execute(
                "SELECT * FROM itens ORDER BY id"
            ).fetchall()
        return {
            "formato": "TECNO_FREITAS_BACKUP",
            "versao": 1,
            "exportado_em": data_atual(),
            "vendas": [dict(v) for v in vendas],
            "itens": [dict(i) for i in itens],
        }

    def importar_json(self, dados):
        if not isinstance(dados, dict) or dados.get("formato") != "TECNO_FREITAS_BACKUP":
            raise ValueError("Este ficheiro não é uma cópia válida.")
        vendas = dados.get("vendas")
        itens = dados.get("itens")
        if not isinstance(vendas, list) or not isinstance(itens, list):
            raise ValueError("A cópia de segurança está incompleta.")

        ids = set()
        for v in vendas:
            vid = int(v["id"])
            total = float(v["total"])
            if vid <= 0 or vid in ids or not math.isfinite(total) or total < 0:
                raise ValueError("Existe um registo de venda inválido.")
            if not isinstance(v.get("data"), str):
                raise ValueError("A data de uma venda é inválida.")
            ids.add(vid)

        item_ids = set()
        for item in itens:
            iid = int(item["id"])
            if iid <= 0 or iid in item_ids:
                raise ValueError("Existe um ID de produto inválido.")
            item_ids.add(iid)
            if int(item["venda_id"]) not in ids:
                raise ValueError("Existe um produto sem venda.")
            preco = float(item["preco"])
            subtotal = float(item["subtotal"])
            qtd = int(item["quantidade"])
            if (
                not math.isfinite(preco) or not math.isfinite(subtotal)
                or preco < 0 or subtotal < 0 or qtd <= 0
                or not str(item["nome"]).strip()
            ):
                raise ValueError("Existe um produto inválido.")

        with self.ligar() as db:
            db.execute("DELETE FROM itens")
            db.execute("DELETE FROM vendas")
            for v in vendas:
                db.execute(
                    "INSERT INTO vendas (id, data, total) VALUES (?, ?, ?)",
                    (int(v["id"]), str(v["data"]), float(v["total"]))
                )
            for item in itens:
                db.execute("""
                    INSERT INTO itens
                    (id, venda_id, nome, preco, quantidade, subtotal)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    int(item["id"]), int(item["venda_id"]),
                    str(item["nome"]), float(item["preco"]),
                    int(item["quantidade"]), float(item["subtotal"])
                ))


class TelaVendas(BoxLayout):
    def __init__(self, base, **kwargs):
        super().__init__(
            orientation="vertical", padding=dp(12), spacing=dp(8), **kwargs
        )
        self.base = base
        self.produtos = []

        cabecalho = BoxLayout(
            orientation="horizontal", size_hint_y=None,
            height=dp(65), spacing=dp(8)
        )
        logo_path = os.path.join(os.path.dirname(__file__), "logo_tf.png")
        if os.path.isfile(logo_path):
            cabecalho.add_widget(Image(
                source=logo_path, size_hint_x=0.30,
                allow_stretch=True, keep_ratio=True
            ))
        else:
            cabecalho.add_widget(Label(
                text="[b]TECNO FREITAS[/b]", markup=True,
                font_size=dp(19), color=cor(COR_VERDE)
            ))
        cabecalho.add_widget(Label(
            text="Sistema de Vendas", font_size=dp(15),
            color=cor(COR_BRANCO)
        ))
        self.add_widget(cabecalho)

        nav = BoxLayout(size_hint_y=None, height=dp(43), spacing=dp(5))
        for texto, pagina in [
            ("VENDER", "vender"),
            ("HISTÓRICO", "historico"),
            ("RESUMO", "resumo"),
        ]:
            btn = Button(
                text=texto, background_normal="",
                background_color=cor(COR_AZUL), font_size=dp(11)
            )
            btn.bind(on_press=lambda _, p=pagina: self.mostrar_pagina(p))
            nav.add_widget(btn)
        self.add_widget(nav)

        self.area = BoxLayout(orientation="vertical")
        self.add_widget(self.area)
        self.mostrar_pagina("vender")

    def botao(self, texto, callback, cor_hex=COR_AZUL, altura=48):
        btn = Button(
            text=texto, size_hint_y=None, height=dp(altura),
            background_normal="", background_color=cor(cor_hex),
            color=cor(COR_BRANCO)
        )
        btn.bind(on_press=callback)
        return btn

    def campo(self, dica, filtro=None):
        return TextInput(
            hint_text=dica, multiline=False, input_filter=filtro,
            size_hint_y=None, height=dp(45), padding=dp(10),
            background_color=cor(COR_CINZA),
            foreground_color=cor(COR_BRANCO),
            cursor_color=cor(COR_VERDE)
        )

    def rotulo(self, texto, tamanho=15, cor_hex=COR_BRANCO):
        return Label(
            text=texto, font_size=dp(tamanho), color=cor(cor_hex),
            size_hint_y=None, height=dp(32),
            halign="left", valign="middle"
        )

    def mensagem(self, titulo, texto):
        conteudo = BoxLayout(
            orientation="vertical", padding=dp(12), spacing=dp(10)
        )
        lbl = Label(
            text=texto, color=cor(COR_BRANCO),
            halign="center", valign="middle"
        )
        lbl.bind(size=lambda obj, size: setattr(obj, "text_size", size))
        conteudo.add_widget(lbl)
        popup = Popup(
            title=titulo, content=conteudo,
            size_hint=(0.88, None), height=dp(200)
        )
        conteudo.add_widget(self.botao("OK", lambda _: popup.dismiss()))
        popup.open()

    def mostrar_pagina(self, pagina):
        self.area.clear_widgets()
        if pagina == "vender":
            self.pagina_vender()
        elif pagina == "historico":
            self.pagina_historico()
        elif pagina == "resumo":
            self.pagina_resumo()

    def pagina_vender(self):
        self.produtos = []
        self.nome = self.campo("Nome do produto")
        self.preco = self.campo("Preço em Kz (ex.: 1500,50)")
        self.qtd = self.campo("Quantidade", "int")
        self.area.add_widget(self.nome)
        self.area.add_widget(self.preco)
        self.area.add_widget(self.qtd)
        self.area.add_widget(self.botao(
            "ADICIONAR PRODUTO", self.adicionar_produto, COR_AZUL
        ))

        self.lista = BoxLayout(
            orientation="vertical", spacing=dp(4), size_hint_y=None
        )
        self.lista.bind(minimum_height=self.lista.setter("height"))
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(self.lista)
        self.area.add_widget(scroll)
        self.total_label = self.rotulo("TOTAL: 0.00 Kz", 20, COR_VERDE)
        self.area.add_widget(self.total_label)
        self.area.add_widget(self.botao(
            "FINALIZAR VENDA", self.finalizar_venda, COR_VERDE
        ))

    def adicionar_produto(self, instance):
        nome = self.nome.text.strip()
        preco_texto = self.preco.text.strip().replace(",", ".")
        qtd_texto = self.qtd.text.strip()
        if not nome or not preco_texto or not qtd_texto:
            self.mensagem("Campos obrigatórios", "Preenche o nome, o preço e a quantidade.")
            return
        try:
            preco = float(preco_texto)
            qtd = int(qtd_texto)
        except ValueError:
            self.mensagem("Dados inválidos", "Verifica o preço e a quantidade.")
            return
        if not math.isfinite(preco) or preco <= 0 or qtd <= 0:
            self.mensagem("Valores inválidos", "O preço e a quantidade devem ser superiores a zero.")
            return

        subtotal = round(preco * qtd, 2)
        self.produtos.append({
            "nome": nome, "preco": preco,
            "quantidade": qtd, "subtotal": subtotal
        })
        linha = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(4))
        linha.add_widget(Label(
            text=f"{nome} x{qtd}", color=cor(COR_BRANCO),
            halign="left", shorten=True
        ))
        linha.add_widget(Label(
            text=dinheiro(subtotal), color=cor(COR_VERDE),
            font_size=dp(11), size_hint_x=0.48
        ))
        self.lista.add_widget(linha)
        total = sum(p["subtotal"] for p in self.produtos)
        self.total_label.text = f"TOTAL: {dinheiro(total)}"
        self.nome.text = ""
        self.preco.text = ""
        self.qtd.text = ""
        self.nome.focus = True

    def finalizar_venda(self, instance):
        if not self.produtos:
            self.mensagem("Venda vazia", "Adiciona pelo menos um produto.")
            return
        try:
            venda_id, total = self.base.registar_venda(self.produtos)
        except (sqlite3.Error, ValueError) as erro:
            self.mensagem("Erro ao guardar", f"Não foi possível guardar a venda.\n{erro}")
            return

        recibo = self.criar_recibo(venda_id)
        caixa = BoxLayout(
            orientation="vertical", padding=dp(10), spacing=dp(8)
        )
        caixa.add_widget(Label(
            text=f"Venda #{venda_id} guardada com sucesso!\n\nTotal: {dinheiro(total)}",
            color=cor(COR_BRANCO)
        ))
        popup = Popup(
            title="Venda concluída", content=caixa,
            size_hint=(0.9, None), height=dp(240)
        )
        caixa.add_widget(self.botao(
            "VER RECIBO",
            lambda _: (popup.dismiss(), self.mostrar_recibo(recibo)),
            COR_AZUL
        ))
        caixa.add_widget(self.botao(
            "NOVA VENDA",
            lambda _: (popup.dismiss(), self.mostrar_pagina("vender")),
            COR_VERDE
        ))
        popup.open()

    def criar_recibo(self, venda_id):
        venda, itens = self.base.obter_venda(venda_id)
        if venda is None:
            return "Venda não encontrada."
        linhas = [
            "================================",
            "         TECNO FREITAS",
            "        RECIBO DE VENDA",
            "================================",
            f"Venda: #{venda['id']}",
            f"Data: {venda['data']}",
            "--------------------------------",
        ]
        for item in itens:
            linhas.extend([
                str(item["nome"]),
                f"  {item['quantidade']} x {dinheiro(item['preco'])}",
                f"  Subtotal: {dinheiro(item['subtotal'])}",
            ])
        linhas.extend([
            "--------------------------------",
            f"TOTAL: {dinheiro(venda['total'])}",
            "================================",
            "       Obrigado pela preferência!",
            "================================",
        ])
        return "\n".join(linhas)

    def mostrar_recibo(self, texto):
        conteudo = BoxLayout(
            orientation="vertical", padding=dp(10), spacing=dp(8)
        )
        campo = TextInput(
            text=texto, readonly=True, multiline=True,
            background_color=cor(COR_CINZA),
            foreground_color=cor(COR_BRANCO)
        )
        conteudo.add_widget(campo)
        popup = Popup(
            title="Recibo", content=conteudo, size_hint=(0.94, 0.85)
        )
        conteudo.add_widget(self.botao("FECHAR", lambda _: popup.dismiss()))
        popup.open()

    def pagina_historico(self):
        self.area.add_widget(self.rotulo("HISTÓRICO DE VENDAS", 18))
        vendas = self.base.listar_vendas()
        if not vendas:
            self.area.add_widget(self.rotulo("Ainda não existem vendas registadas."))
            return

        lista = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=dp(5)
        )
        lista.bind(minimum_height=lista.setter("height"))
        for venda in vendas:
            linha = BoxLayout(size_hint_y=None, height=dp(65), spacing=dp(5))
            linha.add_widget(Label(
                text=f"Venda #{venda['id']}\n{venda['data']}\n{dinheiro(venda['total'])}",
                color=cor(COR_BRANCO), font_size=dp(12), halign="left"
            ))
            btn = Button(
                text="RECIBO", size_hint_x=0.34,
                background_normal="", background_color=cor(COR_AZUL)
            )
            btn.bind(
                on_press=lambda _, vid=venda["id"]:
                self.mostrar_recibo(self.criar_recibo(vid))
            )
            linha.add_widget(btn)
            lista.add_widget(linha)
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(lista)
        self.area.add_widget(scroll)

    def pagina_resumo(self):
        resumo = self.base.resumo()
        self.area.add_widget(self.rotulo("RESUMO DAS VENDAS", 20, COR_VERDE))
        self.area.add_widget(self.rotulo(f"Total de vendas: {resumo['quantidade']}", 17))
        self.area.add_widget(self.rotulo(
            f"Total vendido: {dinheiro(resumo['total'])}", 17, COR_VERDE
        ))
        self.area.add_widget(self.rotulo(
            f"Média por venda: {dinheiro(resumo['media'])}", 16
        ))
        self.area.add_widget(Widget())
        self.area.add_widget(self.botao(
            "EXPORTAR CÓPIA DE SEGURANÇA", self.exportar_backup, COR_AZUL
        ))
        self.area.add_widget(self.botao(
            "RESTAURAR CÓPIA DE SEGURANÇA", self.importar_backup, COR_VERDE
        ))

    def exportar_backup(self, instance):
        texto = json.dumps(
            self.base.exportar_json(), ensure_ascii=False, indent=2
        )
        if sys.platform == "android":
            try:
                from jnius import autoclass
                Intent = autoclass("android.content.Intent")
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
                intent.addCategory(Intent.CATEGORY_OPENABLE)
                intent.setType("application/json")
                intent.putExtra(Intent.EXTRA_TITLE, "tecno_freitas_backup.json")
                self._backup_pendente = texto
                self._atividade = PythonActivity.mActivity
                self._atividade.bind(on_activity_result=self._resultado_android)
                self._atividade.startActivityForResult(intent, 731)
            except Exception as erro:
                self.mensagem("Exportação", f"Não foi possível abrir o seletor Android.\n{erro}")
        else:
            try:
                caminho = os.path.join(
                    App.get_running_app().user_data_dir,
                    "tecno_freitas_backup.json"
                )
                with open(caminho, "w", encoding="utf-8") as ficheiro:
                    ficheiro.write(texto)
                self.mensagem("Cópia criada", f"Ficheiro guardado em:\n{caminho}")
            except OSError as erro:
                self.mensagem("Erro", str(erro))

    def importar_backup(self, instance):
        if sys.platform != "android":
            self.mensagem(
                "Restaurar cópia",
                "A seleção de ficheiros para restauro está disponível na versão Android."
            )
            return
        try:
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType("application/json")
            self._atividade = PythonActivity.mActivity
            self._atividade.bind(on_activity_result=self._resultado_android)
            self._atividade.startActivityForResult(intent, 732)
        except Exception as erro:
            self.mensagem("Importação", f"Não foi possível abrir o seletor Android.\n{erro}")

    def _resultado_android(self, request_code, result_code, intent):
        if intent is None or request_code not in (731, 732):
            return
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            resolver = activity.getContentResolver()
            uri = intent.getData()
            if uri is None:
                return

            if request_code == 731:
                stream = resolver.openOutputStream(uri)
                if stream is None:
                    raise OSError("Não foi possível abrir o ficheiro.")
                try:
                    stream.write(self._backup_pendente.encode("utf-8"))
                    stream.flush()
                finally:
                    stream.close()
                self.mensagem("Cópia exportada", "A cópia de segurança foi guardada.")
            else:
                stream = resolver.openInputStream(uri)
                if stream is None:
                    raise OSError("Não foi possível ler o ficheiro.")
                try:
                    reader_cls = autoclass("java.io.BufferedReader")
                    input_reader_cls = autoclass("java.io.InputStreamReader")
                    reader = reader_cls(input_reader_cls(stream, "UTF-8"))
                    partes = []
                    linha = reader.readLine()
                    while linha is not None:
                        partes.append(str(linha))
                        linha = reader.readLine()
                    reader.close()
                finally:
                    stream.close()

                dados = json.loads("\n".join(partes))
                self.base.importar_json(dados)
                self.mensagem(
                    "Restauro concluído",
                    "O histórico foi restaurado. Os dados anteriores foram substituídos."
                )
                self.mostrar_pagina("resumo")
        except Exception as erro:
            self.mensagem("Erro na cópia de segurança", str(erro))


class VendasApp(App):
    def build(self):
        self.title = NOME_APP
        caminho = os.path.join(self.user_data_dir, "tecno_freitas.db")
        return TelaVendas(BaseDados(caminho))


if __name__ == "__main__":
    VendasApp().run()

"""Holograma da ATENA desenhado pela placa de vídeo (OpenGL 3.3 + shaders).

Camadas (todas somando luz):
  1. Globo geodésico denso (malha de triângulos) + globo interno girando ao contrário
  2. Rede neural na superfície, com pulsos de luz correndo pelas conexões
  3. Nós da rede piscando
  4. Anéis de giroscópio tracejados em eixos diferentes
  5. Milhares de partículas orbitando + núcleo de partículas em redemoinho
  6. HUD na tela: brilho do núcleo, equalizador circular (voz), ondas de fala, régua externa
  7. Bloom: o brilho "vaza" em volta das linhas, como holograma de verdade

Se o PC não tiver OpenGL 3.3, a ATENA usa o holograma simples (holograma.py).
"""
from __future__ import annotations

import math
import time

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (QColor, QMatrix4x4, QOffscreenSurface, QOpenGLContext, QSurfaceFormat, QVector3D)
from PySide6.QtOpenGL import (QOpenGLBuffer, QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat,
                              QOpenGLShader, QOpenGLShaderProgram, QOpenGLVertexArrayObject)
from PySide6.QtOpenGLWidgets import QOpenGLWidget

# ---- constantes OpenGL
GL_FLOAT, GL_LINES, GL_POINTS, GL_TRIANGLE_STRIP = 0x1406, 0x0001, 0x0000, 0x0005
GL_BLEND, GL_ONE, GL_DEPTH_TEST, GL_PROGRAM_POINT_SIZE, GL_MULTISAMPLE = 0x0BE2, 1, 0x0B71, 0x8642, 0x809D
GL_COLOR_BUFFER_BIT, GL_FRAMEBUFFER, GL_TEXTURE_2D, GL_TEXTURE0 = 0x4000, 0x8D40, 0x0DE1, 0x84C0
GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER, GL_LINEAR = 0x2801, 0x2800, 0x2601
GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE = 0x2802, 0x2803, 0x812F
GL_RGBA16F = 0x881A
N_BANDAS = 48

_GL_OK: bool | None = None


def gl_disponivel() -> bool:
    """Testa uma vez se dá pra criar um contexto OpenGL 3.3 (precisa de QApplication criado)."""
    global _GL_OK
    if _GL_OK is None:
        try:
            fmt = _formato()
            sup = QOffscreenSurface()
            sup.setFormat(fmt)
            sup.create()
            ctx = QOpenGLContext()
            ctx.setFormat(fmt)
            ok = ctx.create() and ctx.makeCurrent(sup)
            if ok:
                v = ctx.format()
                ok = (v.majorVersion(), v.minorVersion()) >= (3, 3)
                ctx.doneCurrent()
            _GL_OK = bool(ok)
        except Exception as e:
            print(f"[holograma] OpenGL indisponível: {e}")
            _GL_OK = False
    return _GL_OK


def _formato() -> QSurfaceFormat:
    f = QSurfaceFormat()
    f.setVersion(3, 3)
    f.setProfile(QSurfaceFormat.CoreProfile)
    f.setAlphaBufferSize(8)
    f.setSamples(0)
    return f


# ======================================================================
#  Geometria (gerada uma vez, em numpy)
# ======================================================================
def icosfera(subdivisoes: int) -> tuple[np.ndarray, np.ndarray]:
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
         (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
         (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    verts = [np.array(p, dtype=np.float64) / np.linalg.norm(p) for p in v]
    cache: dict = {}

    def meio(a, b):
        chave = (min(a, b), max(a, b))
        if chave not in cache:
            m = verts[a] + verts[b]
            verts.append(m / np.linalg.norm(m))
            cache[chave] = len(verts) - 1
        return cache[chave]

    for _ in range(subdivisoes):
        novas = []
        for a, b, c in f:
            ab, bc, ca = meio(a, b), meio(b, c), meio(c, a)
            novas += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        f = novas
    arestas = set()
    for a, b, c in f:
        for x, y in ((a, b), (b, c), (c, a)):
            arestas.add((min(x, y), max(x, y)))
    V = np.array(verts, dtype=np.float32)
    E = np.array(sorted(arestas), dtype=np.int32)
    return V, E


def _linhas(V: np.ndarray, E: np.ndarray) -> np.ndarray:
    return V[E.reshape(-1)].astype(np.float32)


def rede_neural(n_nos=210, vizinhos=3, segmentos=12, semente=11):
    rng = np.random.default_rng(semente)
    i = np.arange(n_nos) + 0.5
    phi = np.arccos(1 - 2 * i / n_nos)
    theta = math.pi * (1 + 5 ** 0.5) * i
    nos = np.stack([np.cos(theta) * np.sin(phi), np.cos(phi), np.sin(theta) * np.sin(phi)], 1)
    nos += rng.normal(0, 0.05, nos.shape)
    nos /= np.linalg.norm(nos, axis=1, keepdims=True)
    d = nos @ nos.T
    np.fill_diagonal(d, -9)
    pares = set()
    for a in range(n_nos):
        for b in np.argsort(-d[a])[:vizinhos]:
            pares.add((min(a, int(b)), max(a, int(b))))
    dados = []
    for a, b in pares:
        fase, vel = rng.uniform(0, 1), rng.uniform(0.25, 0.9)
        pa, pb = nos[a], nos[b]
        pts = []
        for k in range(segmentos + 1):
            s = k / segmentos
            p = pa * (1 - s) + pb * s
            p = p / np.linalg.norm(p) * (1.0 + 0.06 * math.sin(math.pi * s))   # arco levemente pra fora
            pts.append((p, s))
        for k in range(segmentos):
            for p, s in (pts[k], pts[k + 1]):
                dados.append([*p, s, fase, vel])
    nos_dados = np.concatenate([nos, rng.uniform(0, 1, (n_nos, 1))], 1)
    return np.array(dados, dtype=np.float32), nos_dados.astype(np.float32)


def particulas(n, raio_min, raio_max, tam_min, tam_max, semente):
    rng = np.random.default_rng(semente)
    raio = rng.uniform(raio_min, raio_max, n) ** 1.0
    theta = rng.uniform(0, 2 * math.pi, n)
    phi = np.arcsin(rng.uniform(-1, 1, n)) * rng.uniform(0.35, 1.0, n)  # mais perto do "equador"
    vel = rng.uniform(0.05, 0.45, n) * rng.choice([-1, 1], n)
    tam = rng.uniform(tam_min, tam_max, n)
    sem = rng.uniform(0, 1, n)
    return np.stack([raio, theta, phi, vel, tam, sem], 1).astype(np.float32)


def circulo(n=240) -> np.ndarray:
    a = np.linspace(0, 2 * math.pi, n + 1)
    pts = []
    for k in range(n):
        for j in (k, k + 1):
            pts.append([math.cos(a[j]), 0.0, math.sin(a[j]), a[j]])
    return np.array(pts, dtype=np.float32)


# ======================================================================
#  Shaders
# ======================================================================
CABECALHO = "#version 330 core\n"
COMUM_VS = """
uniform mat4 u_mvp; uniform mat4 u_modelo; uniform float u_t; uniform float u_escala; uniform float u_audio;
float prof(vec4 m, float r){ return clamp(m.z / (r * u_escala) * 0.5 + 0.5, 0.0, 1.0); }
"""

VS_MALHA = CABECALHO + COMUM_VS + """
layout(location=0) in vec3 a_pos;
out float v_prof;
uniform float u_raio;
float ruido(vec3 p){ return sin(p.x*3.1+u_t*2.3)*sin(p.y*2.7-u_t*1.7)*sin(p.z*3.3+u_t*1.3); }
void main(){
  vec3 p = a_pos * u_raio * u_escala;
  p *= 1.0 + u_audio * 0.10 * ruido(a_pos * 2.0);
  vec4 m = u_modelo * vec4(p, 1.0);
  v_prof = prof(m, u_raio);
  gl_Position = u_mvp * m;
}"""
FS_MALHA = CABECALHO + """
in float v_prof; out vec4 o; uniform vec3 u_cor; uniform float u_alfa;
void main(){ o = vec4(u_cor * mix(0.07, 0.85, pow(v_prof, 1.7)) * u_alfa, 1.0); }"""

VS_REDE = CABECALHO + COMUM_VS + """
layout(location=0) in vec3 a_pos; layout(location=1) in float a_s;
layout(location=2) in float a_fase; layout(location=3) in float a_vel;
uniform float u_vel_pulso;
out float v_prof; out float v_pulso;
void main(){
  vec4 m = u_modelo * vec4(a_pos * u_escala * 1.04, 1.0);
  v_prof = prof(m, 1.04);
  float x = fract(u_t * a_vel * u_vel_pulso + a_fase) * 1.4 - 0.2;
  float dx = (x - a_s) * 6.5; v_pulso = exp(-dx * dx);
  gl_Position = u_mvp * m;
}"""
FS_REDE = CABECALHO + """
in float v_prof; in float v_pulso; out vec4 o;
uniform vec3 u_cor; uniform vec3 u_cor2; uniform float u_alfa; uniform float u_forca;
void main(){
  float b = (0.06 + v_pulso * u_forca) * mix(0.05, 1.0, pow(v_prof, 1.4));
  o = vec4(mix(u_cor, u_cor2, clamp(v_pulso * 1.2, 0.0, 1.0)) * b * u_alfa, 1.0);
}"""

VS_NOS = CABECALHO + COMUM_VS + """
layout(location=0) in vec3 a_pos; layout(location=1) in float a_sem;
uniform float u_dpr; out float v_b;
void main(){
  vec4 m = u_modelo * vec4(a_pos * u_escala * 1.04, 1.0);
  float pr = prof(m, 1.04);
  float tw = 0.45 + 0.55 * sin(u_t * (1.2 + a_sem * 2.5) + a_sem * 30.0);
  v_b = pr * pr * (0.4 + 0.6 * tw);
  gl_PointSize = (2.0 + 3.5 * pr * tw) * u_dpr;
  gl_Position = u_mvp * m;
}"""
FS_PONTO = CABECALHO + """
in float v_b; out vec4 o; uniform vec3 u_cor; uniform float u_alfa;
void main(){
  vec2 c = gl_PointCoord * 2.0 - 1.0; float d = dot(c, c);
  if (d > 1.0) discard;
  float a = exp(-d * 3.5);
  o = vec4(mix(u_cor, vec3(1.0), a * 0.55) * a * v_b * u_alfa, 1.0);
}"""

VS_ANEL = CABECALHO + COMUM_VS + """
layout(location=0) in vec3 a_pos; layout(location=1) in float a_ang;
uniform mat4 u_anel; uniform float u_raio; out float v_prof; out float v_ang;
void main(){
  vec4 m = u_modelo * u_anel * vec4(a_pos * u_raio * u_escala, 1.0);
  v_prof = prof(m, u_raio); v_ang = a_ang;
  gl_Position = u_mvp * m;
}"""
FS_ANEL = CABECALHO + """
in float v_prof; in float v_ang; out vec4 o;
uniform vec3 u_cor; uniform float u_alfa; uniform float u_tracos; uniform float u_vazio; uniform float u_giro;
void main(){
  float f = fract(v_ang / 6.2831853 * u_tracos + u_giro);
  if (f < u_vazio) discard;
  o = vec4(u_cor * mix(0.10, 0.9, v_prof) * u_alfa, 1.0);
}"""

VS_PART = CABECALHO + COMUM_VS + """
layout(location=0) in float a_raio; layout(location=1) in float a_theta; layout(location=2) in float a_phi;
layout(location=3) in float a_vel; layout(location=4) in float a_tam; layout(location=5) in float a_sem;
uniform float u_vel; uniform float u_expandir; uniform float u_dpr; uniform float u_redemoinho;
out float v_b;
void main(){
  float ang = a_theta + u_t * a_vel * u_vel * (1.0 + u_redemoinho / max(a_raio, 0.05));
  float r = a_raio * (1.0 + u_expandir * a_sem);
  vec3 p = vec3(cos(a_phi) * cos(ang), sin(a_phi), cos(a_phi) * sin(ang)) * r;
  vec4 m = u_modelo * vec4(p * u_escala, 1.0);
  float pr = prof(m, max(r, 0.3));
  float tw = 0.5 + 0.5 * sin(u_t * (1.5 + a_sem * 3.0) + a_sem * 40.0);
  v_b = (0.25 + 0.75 * tw) * mix(0.15, 1.0, pr);
  gl_PointSize = a_tam * u_dpr * (0.55 + 0.9 * pr) * (1.0 + u_audio * 0.7);
  gl_Position = u_mvp * m;
}"""

VS_QUAD = CABECALHO + """
layout(location=0) in vec2 a_pos; out vec2 v_uv;
void main(){ v_uv = a_pos * 0.5 + 0.5; gl_Position = vec4(a_pos, 0.0, 1.0); }"""

FS_HUD = CABECALHO + f"""
in vec2 v_uv; out vec4 o;
uniform vec2 u_res; uniform float u_R; uniform float u_t; uniform float u_energia; uniform float u_fala;
uniform float u_alfa; uniform vec3 u_cor; uniform vec3 u_cor2; uniform float u_bandas[{N_BANDAS}];
uniform float u_ondas[6]; uniform float u_giro;
void main(){{
  vec2 p = (v_uv * u_res - u_res * 0.5) / u_R;
  float r = length(p); float a = atan(p.y, p.x);
  vec3 col = vec3(0.0);
  // brilho do núcleo
  col += u_cor2 * exp(-r * r * 60.0) * (0.35 + 0.9 * u_energia);
  col += u_cor * exp(-r * r * 6.0) * 0.10 * (0.5 + u_energia);
  // equalizador circular
  float n = {float(N_BANDAS)};
  float pos = (a / 6.2831853 + 0.5) * n;
  int i = int(mod(floor(pos), n));
  float fr = fract(pos);
  float banda = u_bandas[i];
  float r0 = 0.30;
  float tam = 0.025 + banda * 0.30 * u_fala;
  float barra = step(0.22, fr) * step(fr, 0.78) * smoothstep(r0 - 0.008, r0, r)
              * (1.0 - smoothstep(r0 + tam - 0.008, r0 + tam, r));
  col += mix(u_cor, u_cor2, clamp(banda * 1.3, 0.0, 1.0)) * barra * (0.12 + 0.75 * u_fala);
  // anel fino em volta do núcleo
  float da = (r - 0.285) * 220.0; col += u_cor * exp(-da * da) * 0.5;
  // ondas da fala
  for (int k = 0; k < 6; k++) {{
    float w = u_ondas[k];
    if (w > 0.0) {{ float rr = 0.33 + w * 1.45; float dw = (r - rr) * 70.0; col += u_cor * (1.0 - w) * 0.55 * exp(-dw * dw); }}
  }}
  // régua externa (HUD)
  float rt = 1.80;
  float ang = (a / 6.2831853 + 0.5) + u_giro;
  float tk = fract(ang * 120.0);
  float longo = step(fract(ang * 12.0), 0.012);
  float alcance = rt - mix(0.035, 0.08, longo);
  float marca = step(tk, 0.16) * smoothstep(alcance - 0.004, alcance, r) * (1.0 - smoothstep(rt, rt + 0.004, r));
  float falha = step(0.18, fract(ang * 3.0 + u_t * 0.02));
  col += u_cor * marca * 0.42 * falha;
  // arcos de varredura
  float dr = (r - 1.92) * 160.0; float arco = exp(-dr * dr) * step(0.62, fract(ang * 2.0 - u_t * 0.08));
  col += u_cor * arco * 0.5;
  o = vec4(col * u_alfa, 1.0);
}}"""

FS_COPIA = CABECALHO + """
in vec2 v_uv; out vec4 o; uniform sampler2D u_tex;
vec3 limpo(vec3 c){ bvec3 ruim = bvec3(isnan(c.x)||isinf(c.x), isnan(c.y)||isinf(c.y), isnan(c.z)||isinf(c.z));
  return any(ruim) ? vec3(0.0) : max(c, vec3(0.0)); }
void main(){ o = vec4(limpo(texture(u_tex, v_uv).rgb), 1.0); }"""

FS_BLUR = CABECALHO + """
in vec2 v_uv; out vec4 o; uniform sampler2D u_tex; uniform vec2 u_dir;
void main(){
  float w[5] = float[](0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);
  vec3 c = texture(u_tex, v_uv).rgb * w[0];
  for (int i = 1; i < 5; i++) {
    c += texture(u_tex, v_uv + u_dir * float(i)).rgb * w[i];
    c += texture(u_tex, v_uv - u_dir * float(i)).rgb * w[i];
  }
  o = vec4(c, 1.0);
}"""

FS_FINAL = CABECALHO + """
in vec2 v_uv; out vec4 o; uniform sampler2D u_cena; uniform sampler2D u_bloom; uniform float u_forca_bloom;
vec3 limpo(vec3 c){ bvec3 ruim = bvec3(isnan(c.x)||isinf(c.x), isnan(c.y)||isinf(c.y), isnan(c.z)||isinf(c.z));
  return any(ruim) ? vec3(0.0) : max(c, vec3(0.0)); }
void main(){
  vec3 c = limpo(texture(u_cena, v_uv).rgb) + limpo(texture(u_bloom, v_uv).rgb) * u_forca_bloom;
  c = vec3(1.0) - exp(-c * 1.35);
  float a = clamp(max(c.r, max(c.g, c.b)) * 1.15, 0.0, 1.0);
  o = vec4(min(c, vec3(a)), a);   // pré-multiplicado: transparente onde não tem luz
}"""


# ======================================================================
#  Widget
# ======================================================================
class OrbeGL(QOpenGLWidget):
    """Mesma interface do Orbe simples: set_estado, set_cores, materializar, nivel_externo, fonte_audio."""

    def __init__(self, tamanho: int = 190, primaria="#2E9BFF", secundaria="#9FE8FF", parent=None,
                 detalhe: float = 1.0):
        super().__init__(parent)
        self.setFormat(_formato())
        self.setFixedSize(tamanho, tamanho)
        self.setAttribute(Qt.WA_AlwaysStackOnTop)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.estado = "dormindo"
        self.nivel_externo = None     # () -> 0..1 (microfone)
        self.fonte_audio = None       # () -> (nivel 0..1, bandas np.array) da voz/microfone
        self.detalhe = detalhe
        self._t0 = time.time()
        self._ultimo = time.time()
        self._giro = 0.0
        self._energia = 0.25
        self._audio = 0.0
        self._bandas = np.zeros(N_BANDAS, dtype=np.float32)
        self._ondas: list[float] = []
        self._mat_t0 = None
        self._prim = QColor(primaria)
        self._sec = QColor(secundaria)
        self._cor = QColor(primaria)
        self._pronto = False
        # qualidade adaptativa: 2 = completa, 1 = sem MSAA e bloom leve, 0 = econômica
        self.qualidade = 2
        self._tempos: list[float] = []
        self._ultimo_quadro = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)   # timer "grosso" do Windows causa engasgos
        self._timer.timeout.connect(self.update)
        self._timer.start(16)

    # ---------------------------------------------------------------- API
    def set_cores(self, primaria: str, secundaria: str) -> None:
        self._prim, self._sec = QColor(primaria), QColor(secundaria)

    def set_estado(self, estado: str) -> None:
        if estado != self.estado and estado == "falando":
            self._ondas.append(0.0)
        self.estado = estado
        self._timer.setInterval(16)

    def materializar(self) -> None:
        self._mat_t0 = time.time()
        self._ondas += [0.0, -0.25]

    # ---------------------------------------------------------------- GL
    def _programa(self, vs: str, fs: str) -> QOpenGLShaderProgram:
        p = QOpenGLShaderProgram(self)
        if not p.addShaderFromSourceCode(QOpenGLShader.Vertex, vs):
            raise RuntimeError("vertex shader: " + p.log())
        if not p.addShaderFromSourceCode(QOpenGLShader.Fragment, fs):
            raise RuntimeError("fragment shader: " + p.log())
        if not p.link():
            raise RuntimeError("link: " + p.log())
        return p

    def _vao(self, dados: np.ndarray, layout: list[int], programa=None):
        """Cria VAO+VBO. layout = tamanho de cada atributo (em floats), na ordem das locations."""
        vao = QOpenGLVertexArrayObject(self)
        vao.create()
        vao.bind()
        vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
        vbo.create()
        vbo.bind()
        vbo.setUsagePattern(QOpenGLBuffer.StaticDraw)
        dados = np.ascontiguousarray(dados, dtype=np.float32)
        vbo.allocate(dados.tobytes(), dados.nbytes)
        passo = sum(layout) * 4
        f = self.context().functions()
        desloc = 0
        for loc, n in enumerate(layout):
            f.glEnableVertexAttribArray(loc)
            programa = programa or self.p_malha
            programa.setAttributeBuffer(loc, GL_FLOAT, desloc, n, passo)
            desloc += n * 4
        vao.release()
        vbo.release()
        return vao, vbo, len(dados)

    def initializeGL(self):
        try:
            self._inicializar()
            self._pronto = True
        except Exception as e:
            print(f"[holograma] erro iniciando OpenGL: {e}")
            self._pronto = False

    def _inicializar(self):
        self.p_malha = self._programa(VS_MALHA, FS_MALHA)
        self.p_rede = self._programa(VS_REDE, FS_REDE)
        self.p_nos = self._programa(VS_NOS, FS_PONTO)
        self.p_anel = self._programa(VS_ANEL, FS_ANEL)
        self.p_part = self._programa(VS_PART, FS_PONTO)
        self.p_hud = self._programa(VS_QUAD, FS_HUD)
        self.p_copia = self._programa(VS_QUAD, FS_COPIA)
        self.p_blur = self._programa(VS_QUAD, FS_BLUR)
        self.p_final = self._programa(VS_QUAD, FS_FINAL)

        d = self.detalhe
        V, E = icosfera(3 if d >= 0.8 else 2)
        self.g_malha = self._vao(_linhas(V, E), [3], self.p_malha)
        V2, E2 = icosfera(1)
        self.g_interna = self._vao(_linhas(V2, E2), [3], self.p_malha)
        rede, nos = rede_neural(int(210 * d), 3, 12)
        self.g_rede = self._vao(rede, [3, 1, 1, 1], self.p_rede)
        self.g_nos = self._vao(nos, [3, 1], self.p_nos)
        self.g_anel = self._vao(circulo(240), [3, 1], self.p_anel)
        self.g_part = self._vao(particulas(int(1800 * d), 1.12, 1.75, 1.0, 2.6, 3), [1, 1, 1, 1, 1, 1], self.p_part)
        self.g_nucleo = self._vao(particulas(int(900 * d), 0.03, 0.24, 0.8, 2.0, 5), [1, 1, 1, 1, 1, 1], self.p_part)
        quad = np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype=np.float32).reshape(4, 2)
        self.g_quad = self._vao(quad, [2], self.p_hud)
        self._fbos = None

    def _criar_fbos(self, w: int, h: int):
        fmt = QOpenGLFramebufferObjectFormat()
        fmt.setInternalTextureFormat(GL_RGBA16F)
        fmt.setSamples(4 if self.qualidade >= 2 else 0)
        cena_ms = QOpenGLFramebufferObject(w, h, fmt)
        fmt1 = QOpenGLFramebufferObjectFormat()
        fmt1.setInternalTextureFormat(GL_RGBA16F)
        cena = QOpenGLFramebufferObject(w, h, fmt1)
        hw, hh = max(1, w // 2), max(1, h // 2)
        a = QOpenGLFramebufferObject(hw, hh, fmt1)
        b = QOpenGLFramebufferObject(hw, hh, fmt1)
        f = self.context().functions()
        for fbo in (cena, a, b):
            f.glBindTexture(GL_TEXTURE_2D, fbo.texture())
            f.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            f.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            f.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            f.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        self._fbos = (w, h, cena_ms, cena, a, b)

    # ---------------------------------------------------------------- animação (CPU)
    def _passo(self):
        agora = time.time()
        dt = min(0.1, agora - self._ultimo)
        self._ultimo = agora
        t = agora - self._t0
        est = self.estado

        nivel, bandas = 0.0, None
        if self.fonte_audio is not None and est in ("falando", "ouvindo"):
            try:
                nivel, bandas = self.fonte_audio()
            except Exception:
                nivel, bandas = 0.0, None
        if est == "ouvindo" and self.nivel_externo and not nivel:
            nivel = self.nivel_externo()
        if est == "falando" and bandas is None:  # sem análise: anima de forma sintética
            nivel = 0.45 + 0.4 * abs(math.sin(t * 7.1) * math.sin(t * 2.9 + 1))
        if bandas is None:
            k = np.arange(N_BANDAS)
            bandas = (0.5 + 0.5 * np.sin(k * 0.7 + t * 6)) * nivel * (0.6 + 0.4 * np.sin(k * 1.9 - t * 3))
        bandas = np.clip(np.asarray(bandas, dtype=np.float32)[:N_BANDAS], 0, 1)
        if len(bandas) < N_BANDAS:
            bandas = np.resize(bandas, N_BANDAS)
        # suaviza: sobe rápido, desce devagar (cara de equalizador)
        sobe = bandas > self._bandas
        self._bandas = np.where(sobe, self._bandas + (bandas - self._bandas) * 0.6, self._bandas * 0.86)
        self._audio += (nivel - self._audio) * (0.5 if nivel > self._audio else 0.15)

        alvo = {"falando": 0.55 + 0.45 * self._audio, "ouvindo": 0.45 + 0.55 * self._audio, "pensando": 0.7,
                "mudo": 0.12, "erro": 0.3}.get(est, 0.28 + 0.08 * math.sin(t * 1.3))
        self._energia += (alvo - self._energia) * 0.15
        vel = {"pensando": 1.4, "falando": 0.55, "ouvindo": 0.45}.get(est, 0.22)
        self._giro += dt * vel
        if est == "falando" and self._audio > 0.55 and np.random.random() < 0.06:
            self._ondas.append(0.0)
        self._ondas = [o + dt * 0.9 for o in self._ondas if o + dt * 0.9 < 1.0][-6:]

        cor_alvo = self._prim
        if est == "erro":
            cor_alvo = QColor("#FF4A5C")
        elif est == "mudo":
            g = int(0.3 * self._prim.red() + 0.5 * self._prim.green() + 0.2 * self._prim.blue())
            cor_alvo = QColor(int(g * 0.55), int(g * 0.6), int(g * 0.68))
        c = self._cor
        self._cor = QColor(int(c.red() + (cor_alvo.red() - c.red()) * 0.1),
                           int(c.green() + (cor_alvo.green() - c.green()) * 0.1),
                           int(c.blue() + (cor_alvo.blue() - c.blue()) * 0.1))
        mat = 1.0
        if self._mat_t0 is not None:
            m = min(1.0, (agora - self._mat_t0) / 1.0)
            mat = 1 - (1 - m) ** 3
            if m >= 1:
                self._mat_t0 = None
        return t, mat

    def _medir_quadro(self):
        """Se os quadros estão demorando (PC ocupado), baixa a qualidade sozinha pra ficar fluido."""
        agora = time.perf_counter()
        if time.time() - self._t0 < 8:   # começo da ATENA carregando tudo: não conta
            self._ultimo_quadro = agora
            return
        if self._ultimo_quadro:
            dt = agora - self._ultimo_quadro
            if dt < 0.5:   # ignora pausas (janela escondida etc.)
                self._tempos.append(dt)
        self._ultimo_quadro = agora
        if len(self._tempos) >= 90:
            self._tempos.sort()
            mediana = self._tempos[len(self._tempos) // 2]
            self._tempos.clear()
            if mediana > 0.026 and self.qualidade > 0:
                self.qualidade -= 1
                self._fbos = None
                print(f"[holograma] quadros lentos ({mediana * 1000:.0f} ms): qualidade {self.qualidade}")

    # ---------------------------------------------------------------- desenho
    def paintGL(self):
        f = self.context().functions()
        if not self._pronto:
            f.glClearColor(0, 0, 0, 0)
            f.glClear(GL_COLOR_BUFFER_BIT)
            return
        t, mat = self._passo()
        self._medir_quadro()
        dpr = self.devicePixelRatioF()
        W, H = int(self.width() * dpr), int(self.height() * dpr)
        if self._fbos is None or self._fbos[0] != W or self._fbos[1] != H:
            self._criar_fbos(W, H)
        _, _, cena_ms, cena, fa, fb = self._fbos
        est = self.estado
        cor = QVector3D(self._cor.redF(), self._cor.greenF(), self._cor.blueF())
        sec = self._sec if est not in ("mudo", "erro") else self._cor
        cor2 = QVector3D(sec.redF(), sec.greenF(), sec.blueF())
        e = self._energia
        escala = 0.35 + 0.65 * mat
        alfa = mat

        # câmera
        proj = QMatrix4x4()
        proj.perspective(29.0, W / max(1, H), 0.1, 100.0)
        proj.translate(0, 0, -7.25)
        modelo = QMatrix4x4()
        modelo.rotate(22 + 5 * math.sin(t * 0.4), 1, 0, 0)
        modelo.rotate(math.degrees(self._giro), 0, 1, 0)
        modelo.rotate(7 * math.sin(t * 0.3), 0, 0, 1)

        cena_ms.bind()
        f.glViewport(0, 0, W, H)
        f.glClearColor(0, 0, 0, 0)
        f.glClear(GL_COLOR_BUFFER_BIT)
        f.glDisable(GL_DEPTH_TEST)
        f.glEnable(GL_BLEND)
        f.glBlendFunc(GL_ONE, GL_ONE)
        f.glEnable(GL_PROGRAM_POINT_SIZE)
        if self.qualidade >= 2:
            f.glEnable(GL_MULTISAMPLE)

        def comuns(p, modelo_=modelo):
            p.bind()
            p.setUniformValue("u_mvp", proj)
            p.setUniformValue("u_modelo", modelo_)
            p.setUniformValue1f("u_t", t)
            p.setUniformValue1f("u_escala", escala)
            p.setUniformValue1f("u_audio", self._audio if est in ("falando", "ouvindo") else 0.0)
            p.setUniformValue1f("u_alfa", alfa)

        def desenhar(g, modo, fracao=1.0):
            vao, _, n = g
            vao.bind()
            f.glDrawArrays(modo, 0, max(1, int(n * fracao)))
            vao.release()

        menos = 1.0 if self.qualidade >= 1 else 0.5

        # 1) globo geodésico + globo interno
        comuns(self.p_malha)
        self.p_malha.setUniformValue("u_cor", cor)
        self.p_malha.setUniformValue1f("u_raio", 1.0)
        self.p_malha.setUniformValue1f("u_alfa", alfa * (0.55 + 0.6 * e))
        desenhar(self.g_malha, GL_LINES)
        interno = QMatrix4x4(modelo)
        interno.rotate(math.degrees(-self._giro * 2.2), 0.3, 1, 0.2)
        self.p_malha.setUniformValue("u_modelo", interno)
        self.p_malha.setUniformValue1f("u_raio", 0.56)
        self.p_malha.setUniformValue("u_cor", cor2)
        self.p_malha.setUniformValue1f("u_alfa", alfa * (0.5 + 0.6 * e))
        desenhar(self.g_interna, GL_LINES)

        # 2) rede neural com pulsos
        comuns(self.p_rede)
        self.p_rede.setUniformValue("u_cor", cor)
        self.p_rede.setUniformValue("u_cor2", cor2)
        self.p_rede.setUniformValue1f("u_vel_pulso", 1.6 if est == "pensando" else 0.55)
        self.p_rede.setUniformValue1f("u_forca", 2.2 if est == "pensando" else 1.1 + e)
        desenhar(self.g_rede, GL_LINES)

        # 3) nós
        comuns(self.p_nos)
        self.p_nos.setUniformValue("u_cor", cor2)
        self.p_nos.setUniformValue1f("u_dpr", dpr * (self.width() / 260))
        desenhar(self.g_nos, GL_POINTS)

        # 4) anéis de giroscópio
        rapidez = {"pensando": 2.4, "falando": 1.3, "ouvindo": 1.1}.get(est, 0.6)
        comuns(self.p_anel)
        for i, (raio, eixo, vel, tracos, vazio, c) in enumerate((
                (1.22, (1, 0, 0.3), 38, 36, 0.25, cor), (1.34, (0.2, 0.3, 1), -26, 4, 0.55, cor2),
                (1.46, (0.8, 0.1, -0.6), 18, 90, 0.4, cor), (1.58, (-0.4, 1, 0.2), -11, 2, 0.7, cor2))):
            anel = QMatrix4x4()
            anel.rotate(math.degrees(t * 0.0) + 70 * i, *eixo)
            anel.rotate(t * vel * rapidez, 0, 1, 0)
            self.p_anel.setUniformValue("u_anel", anel)
            self.p_anel.setUniformValue1f("u_raio", raio * (1 + 0.05 * e))
            self.p_anel.setUniformValue("u_cor", c)
            self.p_anel.setUniformValue1f("u_tracos", tracos)
            self.p_anel.setUniformValue1f("u_vazio", vazio)
            self.p_anel.setUniformValue1f("u_giro", t * 0.05 * (i + 1))
            self.p_anel.setUniformValue1f("u_alfa", alfa * (0.7 + 0.8 * e))
            desenhar(self.g_anel, GL_LINES)

        # 5) partículas + núcleo em redemoinho
        comuns(self.p_part)
        self.p_part.setUniformValue1f("u_dpr", dpr * (self.width() / 260))
        self.p_part.setUniformValue("u_cor", cor)
        self.p_part.setUniformValue1f("u_vel", 2.0 if est == "pensando" else 1.0)
        self.p_part.setUniformValue1f("u_expandir", 0.35 * self._audio if est == "falando" else 0.08 * e)
        self.p_part.setUniformValue1f("u_redemoinho", 0.0)
        self.p_part.setUniformValue1f("u_alfa", alfa * (0.22 + 0.35 * e))
        desenhar(self.g_part, GL_POINTS, menos)
        self.p_part.setUniformValue("u_cor", cor2)
        self.p_part.setUniformValue1f("u_vel", 3.0 if est == "pensando" else 1.6)
        self.p_part.setUniformValue1f("u_redemoinho", 0.08)
        self.p_part.setUniformValue1f("u_expandir", 0.6 * self._audio)
        self.p_part.setUniformValue1f("u_alfa", alfa * (0.16 + 0.3 * e))
        desenhar(self.g_nucleo, GL_POINTS, menos)

        # 6) HUD em tela: núcleo, equalizador, ondas, régua
        self.p_hud.bind()
        R = min(W, H) / 2 / 1.98
        self.p_hud.setUniformValue("u_res", float(W), float(H))
        self.p_hud.setUniformValue1f("u_R", R * escala)
        self.p_hud.setUniformValue1f("u_t", t)
        self.p_hud.setUniformValue1f("u_energia", e)
        self.p_hud.setUniformValue1f("u_fala", 1.0 if est == "falando" else (0.6 if est == "ouvindo" else 0.0))
        self.p_hud.setUniformValue1f("u_alfa", alfa)
        self.p_hud.setUniformValue("u_cor", cor)
        self.p_hud.setUniformValue("u_cor2", cor2)
        self.p_hud.setUniformValue1f("u_giro", t * 0.01 * rapidez)
        self.p_hud.setUniformValueArray(self.p_hud.uniformLocation("u_bandas"),
                                        [float(x) for x in self._bandas], N_BANDAS, 1)
        ondas = (self._ondas + [-1.0] * 6)[:6]
        self.p_hud.setUniformValueArray(self.p_hud.uniformLocation("u_ondas"), [float(x) for x in ondas], 6, 1)
        desenhar(self.g_quad, GL_TRIANGLE_STRIP)
        cena_ms.release()

        # 7) bloom
        QOpenGLFramebufferObject.blitFramebuffer(cena, cena_ms)
        f.glDisable(GL_BLEND)
        f.glActiveTexture(GL_TEXTURE0)
        hw, hh = fa.width(), fa.height()

        def passe(destino, programa, textura, **unis):
            destino.bind()
            f.glViewport(0, 0, destino.width(), destino.height())
            programa.bind()
            f.glBindTexture(GL_TEXTURE_2D, textura)
            programa.setUniformValue1i("u_tex", 0)
            for k, v in unis.items():
                programa.setUniformValue(k, *v)
            desenhar(self.g_quad, GL_TRIANGLE_STRIP)
            destino.release()

        passe(fa, self.p_copia, cena.texture())
        for _ in range(2 if self.qualidade >= 2 else 1):
            passe(fb, self.p_blur, fa.texture(), u_dir=(1.6 / hw, 0.0))
            passe(fa, self.p_blur, fb.texture(), u_dir=(0.0, 1.6 / hh))

        # 8) junta tudo na tela (transparente onde não tem luz)
        f.glBindFramebuffer(GL_FRAMEBUFFER, self.defaultFramebufferObject())
        f.glViewport(0, 0, W, H)
        f.glClearColor(0, 0, 0, 0)
        f.glClear(GL_COLOR_BUFFER_BIT)
        self.p_final.bind()
        f.glActiveTexture(GL_TEXTURE0)
        f.glBindTexture(GL_TEXTURE_2D, cena.texture())
        self.p_final.setUniformValue1i("u_cena", 0)
        f.glActiveTexture(GL_TEXTURE0 + 1)
        f.glBindTexture(GL_TEXTURE_2D, fa.texture())
        self.p_final.setUniformValue1i("u_bloom", 1)
        self.p_final.setUniformValue1f("u_forca_bloom", 0.9 + 0.5 * e)
        desenhar(self.g_quad, GL_TRIANGLE_STRIP)
        f.glActiveTexture(GL_TEXTURE0)

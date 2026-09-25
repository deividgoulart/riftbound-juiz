// Tudo que o site pede à API (api/main.py). O endereço vem de NEXT_PUBLIC_API_URL.

/** Aceita o endereço como vier colado: sem "https://", com "/" ou "/docs" no fim. */
export function limparEndereco(bruto: string): string {
  let endereco = bruto.trim().replace(/\/+$/, "").replace(/\/docs$/, "");
  if (endereco && !/^https?:\/\//.test(endereco)) endereco = "https://" + endereco;
  return endereco;
}

// NEXT_PUBLIC_* entra no site na hora do build: criar ou mudar a variável na Vercel pede um Redeploy.
export const API_URL = limparEndereco(process.env.NEXT_PUBLIC_API_URL || "") || "http://localhost:8000";

const CHAVE_DO_TOKEN = "juiz-riftbound:token";

export function lerToken(): string | null {
  try {
    return localStorage.getItem(CHAVE_DO_TOKEN);
  } catch {
    return null;
  }
}

export function guardarToken(token: string | null) {
  try {
    if (token) localStorage.setItem(CHAVE_DO_TOKEN, token);
    else localStorage.removeItem(CHAVE_DO_TOKEN);
  } catch {
    /* navegador sem localStorage: a senha vale só até recarregar */
  }
}

export class ErroDaApi extends Error {
  constructor(public status: number, mensagem: string) {
    super(mensagem);
  }
}

export async function pedir<T>(caminho: string, opcoes: RequestInit = {}): Promise<T> {
  const token = lerToken();
  const headers = new Headers(opcoes.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (opcoes.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let resposta: Response;
  try {
    resposta = await fetch(API_URL + caminho, { ...opcoes, headers });
  } catch {
    throw new ErroDaApi(0, explicarFalhaDeRede());
  }
  if (!resposta.ok) {
    let mensagem = `Erro ${resposta.status}`;
    try {
      const corpo = await resposta.json();
      if (typeof corpo.detail === "string") mensagem = corpo.detail;
      else if (Array.isArray(corpo.detail)) mensagem = "Pedido inválido.";
    } catch {
      /* corpo sem JSON */
    }
    throw new ErroDaApi(resposta.status, mensagem);
  }
  const tipo = resposta.headers.get("content-type") || "";
  return (tipo.includes("application/json") ? resposta.json() : resposta.text()) as Promise<T>;
}

/** O navegador não diz por que o pedido falhou (servidor fora do ar e CORS dão o mesmo erro): o texto
    lista as causas possíveis, com o endereço que o site tentou. */
function explicarFalhaDeRede(): string {
  const noComputador = typeof window !== "undefined" && ["localhost", "127.0.0.1"].includes(window.location.hostname);
  if (API_URL.includes("localhost") && !noComputador) {
    return (
      "O site não sabe o endereço da API: crie a variável NEXT_PUBLIC_API_URL na Vercel (Settings > Environment " +
      "Variables) com o endereço do Render e faça um Redeploy (a variável só entra no site num build novo)."
    );
  }
  return (
    `Não consegui falar com a API (${API_URL}). Se ela estava dormindo, leva até 1 minuto pra acordar: tente de novo. ` +
    `Se continuar, abra ${API_URL}/api/saude no navegador: se abrir, confira se SITE_URL no Render é o endereço ` +
    "deste site; se não abrir, veja os Logs do serviço no Render."
  );
}

export const buscar = <T,>(caminho: string) => pedir<T>(caminho);

// --- Tipos das respostas ---

export type Info = {
  publico: boolean;
  dono: boolean;
  fontes: { faq_data: string | null; faq_commit: string | null; crd_versao: string | null; crd_nome: string | null };
  exemplos: string[];
  privacidade: string;
  creditos: string;
  convidado: { restantes: number; limite: number; bloqueio: string | null } | null;
  avaliacao: boolean;
  turso: boolean;
  topdeck: boolean;
};

export type Fonte = {
  numero: number;
  tipo: "faq" | "crd" | "carta" | "deck";
  rotulo: string;
  titulo: string;
  url: string | null;
  nota: number | null;
  citada: boolean;
  citacao_pendente: boolean;
  trecho: string | null;
};

export type RespostaDoJuiz = {
  id: string;
  html: string;
  original: string;
  tipo: string;
  encontrou: boolean;
  sem_llm: string | null;
  fontes: Fonte[];
  nota: number | null;
  uso: { modelo?: string; tokens_entrada?: number; tokens_saida?: number };
  termos: [string, string][];
  busca: string | null;
  busca_reserva: boolean;
  deck: string | null;
  restantes: number | null;
};

export type Carta = {
  nome: string;
  tipo: string;
  tipos: string[];
  supertipos: string[];
  dominios: string[];
  tags: string[];
  energia: number | null;
  poder: number | null;
  might: number | null;
  codigo: string | null;
  imagem: string | null;
};

export type Colecao = { cartas: Record<string, number>; diferentes: number; copias: number };

export type Lenda = { nome: string; rotulo: string; imagem: string | null; dominios: string[] };

export type ResumoDoDeck = {
  id: string;
  nome: string;
  origem: string;
  url: string | null;
  data: string | null;
  torneio: string | null;
  colocacao: string | null;
  lenda: Lenda | null;
  porcentagem: number;
  tenho: number;
  total: number;
  copias_faltando: number;
  cartas_faltando: number;
  custo: number | null;
  sem_preco: number;
};

export type ListaDeDecks = {
  decks: ResumoDoDeck[];
  total: number;
  ordem: Ordem;
  tem_precos: boolean;
  lendas: (Lenda & { decks: number })[];
  meta: { ultima_coleta: string | null; chave: boolean; dias: number; atualizar_a_cada_dias: number } | null;
};

export type Ordem = "barato" | "faltando";

export type DetalheDoDeck = ResumoDoDeck & {
  cartas: { secao: string; secao_nome: string; carta: string; quantidade: number; tem: number | null; imagem: string | null }[];
  faltando: { carta: string; precisa: number; tem: number; falta: number; imagem: string | null; liga: string }[];
  lista_de_compra: string;
  lista_texto: string;
  compra_por_lista: string;
  legenda_dos_precos: string | null;
};

export type Previa = {
  cartas: { secao: string; secao_nome: string; carta: string; quantidade: number; imagem: string | null }[];
  nao_reconhecidas: { texto: string; sugestoes: string[] }[];
  avisos: string[];
};

export type RelatorioCsv = {
  importadas: number;
  copias: number;
  desconhecidas: { texto: string; sugestoes: string[] }[];
  invalidas: number;
  substituiu: boolean;
};

export type FichaDaCarta = {
  nome: string;
  texto: string | null;
  atributos: { tipos?: string[]; dominios?: string[]; energia?: number | null; poder?: number | null; might?: number | null; tags?: string[] };
  errata: boolean;
  url_wiki: string | null;
  imagem: string | null;
  duvidas: { pergunta: string; url: string; pagina: string }[];
  mecanicas: { pagina: string; url: string }[];
};

export type Trocas = {
  cartas: {
    carta: string;
    tipo: string | null;
    dominios: string[];
    imagem: string | null;
    tenho: number;
    guardar: number;
    excedente: number;
    trocar: number;
    ajustado: boolean;
    liga: string;
  }[];
  copias: number;
  valor: number | null;
  sem_preco: number;
  lista_texto: string;
};

// --- Formatação ---

export function reais(valor: number | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function dataCurta(iso: string | null | undefined): string {
  if (!iso) return "";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

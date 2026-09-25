"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { AlertTriangle, ArrowUp, ChevronDown, CloudOff, Info as InfoIcon, Layers, RefreshCw, RotateCcw, ThumbsDown, ThumbsUp } from "lucide-react";
import { buscar, pedir, type Fonte, type ListaDeDecks, type RespostaDoJuiz } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { Markdown } from "@/components/markdown";
import { Aviso, Chip, Folha, juntar } from "@/components/ui";

type Mensagem = { papel: "user"; texto: string } | { papel: "assistant"; resposta: RespostaDoJuiz };

const CHAVE_DA_CONVERSA = "juiz-riftbound:conversa";

function plural(n: number, singular: string, plural_: string) {
  return `${n} ${n === 1 ? singular : plural_}`;
}

/** Pares (pergunta, resposta) já respondidos, pro juiz entender continuações ("e num showdown?"). */
function historico(mensagens: Mensagem[]): [string, string][] {
  const pares: [string, string][] = [];
  let pergunta: string | null = null;
  for (const m of mensagens) {
    if (m.papel === "user") pergunta = m.texto;
    else if (pergunta !== null) {
      if (!m.resposta.sem_llm) pares.push([pergunta, m.resposta.original]); // no plano B não houve resposta
      pergunta = null;
    }
  }
  return pares.slice(-6);
}

function LinhaDaFonte({ f }: { f: Fonte }) {
  return (
    <li className="flex gap-2 text-sm">
      <span className="shrink-0 font-semibold text-azul">F{f.numero}</span>
      <span className="min-w-0">
        <span className="text-apagado">{f.rotulo} · </span>
        {f.url ? (
          <a href={f.url} target="_blank" rel="noopener noreferrer" className="text-texto underline decoration-linha underline-offset-2 hover:decoration-azul">
            {f.titulo}
          </a>
        ) : (
          f.titulo
        )}
      </span>
    </li>
  );
}

function Resposta({ r, avaliar }: { r: RespostaDoJuiz; avaliar: boolean }) {
  const [fontesAbertas, setFontesAbertas] = useState(false);
  const [voto, setVoto] = useState<boolean | null>(null);
  const citadas = r.fontes.filter((f) => f.citada);
  const outras = r.fontes.filter((f) => !f.citada);

  if (r.sem_llm) {
    return (
      <div className="space-y-3">
        <Aviso tipo="alerta">
          <div className="flex gap-2">
            <CloudOff size={18} className="mt-0.5 shrink-0 text-ouro" />
            <div>
              <p>{r.original}</p>
              <p className="mt-1 text-xs text-apagado">Motivo: {r.sem_llm}. Tente de novo em alguns minutos pra receber a resposta em português.</p>
            </div>
          </div>
        </Aviso>
        {r.fontes.slice(0, 3).map((f) => (
          <div key={f.numero} className="rounded-xl border border-linha bg-fundo/40 p-3">
            <ul>
              <LinhaDaFonte f={f} />
            </ul>
            <p className="mt-2 text-sm leading-relaxed text-apagado">{f.trecho}</p>
          </div>
        ))}
      </div>
    );
  }

  async function votar(gostou: boolean) {
    setVoto(gostou);
    try {
      await pedir("/api/avaliar", { method: "POST", body: JSON.stringify({ id: r.id, gostou }) });
    } catch {
      /* avaliação é só pro registro local */
    }
  }

  return (
    <div className="space-y-3">
      <Markdown texto={r.html} />
      {r.deck && (
        <p className="flex items-center gap-1.5 text-xs text-apagado">
          <Layers size={13} /> Respondido com o deck em foco: {r.deck}
        </p>
      )}
      {r.busca_reserva && (
        <p className="flex items-center gap-1.5 text-xs text-apagado">
          <RefreshCw size={13} /> Busca feita com o modelo reserva ({r.busca}): a busca principal (Gemini) está indisponível agora.
        </p>
      )}
      {citadas.some((f) => f.citacao_pendente) && (
        <Aviso tipo="alerta">
          <span className="flex gap-2">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-ouro" />
            Uma das fontes usadas avisa que o Core Rules ainda não confirma totalmente esta interpretação. Numa partida oficial, confirme com o juiz do evento.
          </span>
        </Aviso>
      )}
      {r.fontes.length > 0 && (
        <div className="rounded-xl border border-linha bg-fundo/40">
          <button type="button" onClick={() => setFontesAbertas(!fontesAbertas)} className="flex w-full items-center justify-between px-3 py-2 text-sm text-apagado">
            <span>
              Fontes ({plural(citadas.length, "citada", "citadas")}
              {outras.length > 0 && `, ${plural(outras.length, "também consultada", "também consultadas")}`})
            </span>
            <ChevronDown size={16} className={juntar("transition", fontesAbertas && "rotate-180")} />
          </button>
          {fontesAbertas && (
            <div className="space-y-2 border-t border-linha px-3 py-3">
              <ul className="space-y-1.5">
                {citadas.map((f) => (
                  <LinhaDaFonte key={f.numero} f={f} />
                ))}
              </ul>
              {outras.length > 0 && (
                <>
                  <p className="pt-1 text-xs text-apagado">Também consultadas, mas não citadas na resposta:</p>
                  <ul className="space-y-1.5">
                    {outras.map((f) => (
                      <LinhaDaFonte key={f.numero} f={f} />
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </div>
      )}
      {avaliar && r.fontes.length > 0 && (
        <div className="flex gap-1">
          {[true, false].map((gostou) => {
            const Icone = gostou ? ThumbsUp : ThumbsDown;
            return (
              <button
                key={String(gostou)}
                type="button"
                onClick={() => votar(gostou)}
                aria-label={gostou ? "Boa resposta" : "Resposta ruim"}
                className={juntar("rounded-lg p-1.5 hover:bg-superficie-2", voto === gostou ? "text-ouro" : "text-apagado")}
              >
                <Icone size={15} />
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function PaginaDoJuiz() {
  const { info, erroDaInfo, recarregarInfo } = useSessao();
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [texto, setTexto] = useState("");
  const [pensando, setPensando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [deckId, setDeckId] = useState("");
  const [sobre, setSobre] = useState(false);
  const fim = useRef<HTMLDivElement>(null);

  const { data: meus } = useSWR<ListaDeDecks>("/api/decks?tipo=meus&ordem=faltando&limite=100", buscar, { revalidateOnFocus: false });
  const { data: doMeta } = useSWR<ListaDeDecks>("/api/decks?tipo=meta&ordem=faltando&limite=30", buscar, { revalidateOnFocus: false });

  useEffect(() => {
    // Vindo da ficha de uma carta ("Perguntar ao juiz sobre esta carta"): a pergunta começa escrita.
    const comecada = new URLSearchParams(window.location.search).get("pergunta");
    if (comecada) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- só existe no navegador
      setTexto(comecada);
      window.history.replaceState(null, "", "/");
      setTimeout(() => document.querySelector<HTMLTextAreaElement>("form textarea")?.focus(), 50);
    }
    try {
      const salva = sessionStorage.getItem(CHAVE_DA_CONVERSA);
      if (salva) setMensagens(JSON.parse(salva));
    } catch {
      /* sem sessionStorage */
    }
  }, []);

  useEffect(() => {
    try {
      sessionStorage.setItem(CHAVE_DA_CONVERSA, JSON.stringify(mensagens));
    } catch {
      /* sem sessionStorage */
    }
    fim.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [mensagens, pensando]);

  const bloqueio = info?.convidado?.bloqueio ?? null;
  const restantes = info?.convidado?.restantes;

  async function perguntar(pergunta: string) {
    pergunta = pergunta.trim();
    if (!pergunta || pensando || bloqueio) return;
    const anteriores = historico(mensagens);
    setMensagens((m) => [...m, { papel: "user", texto: pergunta }]);
    setTexto("");
    setErro(null);
    setPensando(true);
    try {
      const resposta = await pedir<RespostaDoJuiz>("/api/perguntar", {
        method: "POST",
        body: JSON.stringify({ pergunta, historico: anteriores, deck_id: deckId || null }),
      });
      setMensagens((m) => [...m, { papel: "assistant", resposta }]);
    } catch (e) {
      setMensagens((m) => m.slice(0, -1)); // a pergunta volta pra caixa de texto
      setTexto(pergunta);
      setErro((e as Error).message);
    } finally {
      setPensando(false);
      recarregarInfo(); // atualiza as perguntas restantes do convidado
    }
  }

  const decksParaFoco = [...(meus?.decks ?? []).map((d) => ({ ...d, grupo: "Meus decks" })), ...(doMeta?.decks ?? []).map((d) => ({ ...d, grupo: "Do meta" }))];

  return (
    <div className="flex min-h-[calc(100dvh-10rem)] flex-col">
      <header className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h1 className="font-titulo text-2xl font-bold tracking-wide text-ouro md:text-3xl">Juiz de regras</h1>
          <p className="mt-1 text-sm text-apagado">Pergunte em português. As respostas citam o FAQ e o Core Rules oficial.</p>
        </div>
        <div className="flex shrink-0 gap-1">
          {mensagens.length > 0 && (
            <button type="button" onClick={() => setMensagens([])} title="Nova conversa" className="rounded-full p-2 text-apagado hover:bg-superficie-2 hover:text-texto">
              <RotateCcw size={18} />
            </button>
          )}
          <button type="button" onClick={() => setSobre(true)} title="Como funciona" className="rounded-full p-2 text-apagado hover:bg-superficie-2 hover:text-texto">
            <InfoIcon size={18} />
          </button>
        </div>
      </header>

      {decksParaFoco.length > 0 && (
        <label className="mb-4 flex items-center gap-2 rounded-xl border border-linha bg-superficie px-3 py-2 text-sm">
          <Layers size={16} className="shrink-0 text-ouro" />
          <span className="shrink-0 text-apagado">Deck em foco</span>
          <select
            value={deckId}
            onChange={(e) => setDeckId(e.target.value)}
            className="min-w-0 flex-1 truncate bg-transparent text-texto outline-none"
          >
            <option value="">Nenhum</option>
            {["Meus decks", "Do meta"].map((grupo) => {
              const doGrupo = decksParaFoco.filter((d) => d.grupo === grupo);
              return doGrupo.length ? (
                <optgroup key={grupo} label={grupo}>
                  {doGrupo.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.nome}
                    </option>
                  ))}
                </optgroup>
              ) : null;
            })}
          </select>
        </label>
      )}

      {erroDaInfo && <Aviso tipo="erro">{erroDaInfo.message}</Aviso>}

      <div className="flex-1 space-y-4">
        {mensagens.length === 0 && !bloqueio && (
          <div className="rounded-2xl border border-linha bg-superficie p-5">
            <p className="mb-3 text-sm text-apagado">
              O juiz lembra da conversa: dá pra perguntar &quot;e se for durante um showdown?&quot; depois de uma resposta. Experimente:
            </p>
            <div className="flex flex-wrap gap-2">
              {(info?.exemplos ?? []).map((exemplo) => (
                <Chip key={exemplo} onClick={() => perguntar(exemplo)}>
                  {exemplo}
                </Chip>
              ))}
            </div>
          </div>
        )}

        {mensagens.map((m, i) =>
          m.papel === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-md bg-ouro/15 px-4 py-2.5 text-sm text-texto ring-1 ring-ouro/30">{m.texto}</div>
            </div>
          ) : (
            <div key={i} className="rounded-2xl rounded-tl-md border border-linha bg-superficie p-4 text-[15px]">
              <Resposta r={m.resposta} avaliar={!!info?.avaliacao} />
            </div>
          ),
        )}

        {pensando && (
          <div className="flex items-center gap-3 rounded-2xl border border-linha bg-superficie p-4 text-sm text-apagado">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-ouro border-t-transparent" />
            Consultando as regras... (se o servidor estava dormindo, a primeira resposta pode levar 1 minuto)
          </div>
        )}
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        {bloqueio && <Aviso tipo="info">{bloqueio}</Aviso>}
        <div ref={fim} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          perguntar(texto);
        }}
        className="sticky bottom-[calc(4.25rem+env(safe-area-inset-bottom))] mt-4 md:bottom-4"
      >
        {info?.convidado && !bloqueio && restantes !== undefined && (
          <p className="mb-1.5 px-1 text-xs text-apagado">
            Modo convidado: {plural(restantes, "pergunta restante", "perguntas restantes")} hoje. {info.privacidade}
          </p>
        )}
        <div className="flex items-end gap-2 rounded-2xl border border-linha bg-superficie p-2 shadow-2xl shadow-black/40 focus-within:border-ouro/60">
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                perguntar(texto);
              }
            }}
            rows={1}
            maxLength={500}
            disabled={!!bloqueio}
            placeholder="Ex.: a Vex atordoa a unidade que acabou de ser jogada?"
            className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] outline-none placeholder:text-apagado/70"
          />
          <button
            type="submit"
            disabled={!texto.trim() || pensando || !!bloqueio}
            aria-label="Perguntar"
            className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-ouro text-fundo transition disabled:opacity-30"
          >
            <ArrowUp size={20} />
          </button>
        </div>
      </form>

      <Folha aberta={sobre} onFechar={() => setSobre(false)} titulo="Como o juiz funciona">
        <div className="space-y-4 text-sm leading-relaxed">
          <ol className="list-decimal space-y-1.5 pl-5">
            <li>A pergunta é comparada com ~500 trechos do FAQ e do Core Rules usando embeddings (vetores que representam o sentido do texto).</li>
            <li>Os trechos mais parecidos, o texto oficial das regras citadas e o texto das cartas mencionadas vão para um LLM (Gemini), que responde só com base nessas fontes.</li>
            <li>Se nada parecido o bastante for encontrado, o juiz diz que não encontrou, em vez de inventar.</li>
          </ol>
          {info && (
            <p className="text-apagado">
              Versões das fontes: FAQ de {info.fontes.faq_data ?? "?"} (commit {info.fontes.faq_commit ?? "?"}) · Core Rules v{info.fontes.crd_versao ?? "?"}
            </p>
          )}
          {info && (
            <>
              <p>
                <strong>Privacidade:</strong> {info.privacidade}
              </p>
              <Markdown texto={info.creditos} className="resposta text-apagado" />
            </>
          )}
        </div>
      </Folha>
    </div>
  );
}

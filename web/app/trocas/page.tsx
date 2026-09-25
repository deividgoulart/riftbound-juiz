"use client";

import { useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { Check, Copy, Download, Minus, Plus, RotateCcw, Search } from "lucide-react";
import { buscar, pedir, reais, type Carta, type Colecao, type Trocas } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { ImagemDaCarta, NomeDaCarta } from "@/components/carta";
import { Aviso, Botao, Cabecalho, Cartao, Carregando, Chip } from "@/components/ui";

const NOMES_DOS_TIPOS: Record<string, string> = {
  Unit: "Units",
  Spell: "Spells",
  Gear: "Gear",
  Legend: "Lendas",
  Battlefield: "Battlefields",
  Rune: "Runas",
};

function copias(n: number) {
  return n === 1 ? "1 cópia" : `${n} cópias`;
}

/** Busca na coleção pra pôr na lista uma carta que está dentro do limite (ex.: uma repetida que não uso). */
function AdicionarDaColecao({ naLista, onAdicionar }: { naLista: Set<string>; onAdicionar: (carta: string) => void }) {
  const { data: cartas } = useSWR<Carta[]>("/api/cartas", buscar, { revalidateOnFocus: false });
  const { data: colecao } = useSWR<Colecao>("/api/colecao", buscar);
  const [busca, setBusca] = useState("");
  const achadas = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    if (termo.length < 2 || !cartas || !colecao) return [];
    return cartas
      .filter((c) => (colecao.cartas[c.nome] ?? 0) > 0 && !naLista.has(c.nome) && `${c.nome} ${c.tags.join(" ")}`.toLowerCase().includes(termo))
      .slice(0, 6);
  }, [busca, cartas, colecao, naLista]);

  return (
    <div>
      <div className="flex items-center gap-2 rounded-xl border border-linha bg-fundo px-3 focus-within:border-ouro/60">
        <Search size={16} className="text-apagado" />
        <input
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Pôr outra carta da coleção na lista"
          className="w-full bg-transparent py-2.5 text-sm outline-none placeholder:text-apagado/70"
        />
      </div>
      {achadas.length > 0 && (
        <ul className="mt-2 divide-y divide-linha rounded-xl border border-linha">
          {achadas.map((c) => (
            <li key={c.nome}>
              <button
                type="button"
                onClick={() => {
                  onAdicionar(c.nome);
                  setBusca("");
                }}
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-superficie-2"
              >
                <span className="truncate">{c.nome}</span>
                <span className="shrink-0 text-xs text-apagado">tenho {colecao?.cartas[c.nome]} · pôr 1</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function PaginaDasTrocas() {
  const { podeEditar } = useSessao();
  const { data, error, mutate } = useSWR<Trocas>("/api/trocas", buscar);
  const { mutate: mutarGlobal } = useSWRConfig();
  const [tipo, setTipo] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [copiada, setCopiada] = useState(false);

  async function ajustar(carta: string, quantidade: number | null) {
    setOcupado(carta);
    setErro(null);
    try {
      await mutate(await pedir<Trocas>("/api/trocas", { method: "PUT", body: JSON.stringify({ carta, quantidade }) }), { revalidate: false });
      mutarGlobal("/api/colecao");
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setOcupado(null);
    }
  }

  async function copiar() {
    if (!data) return;
    await navigator.clipboard.writeText(data.lista_texto);
    setCopiada(true);
    setTimeout(() => setCopiada(false), 2000);
  }

  function baixar() {
    if (!data) return;
    const url = URL.createObjectURL(new Blob([data.lista_texto], { type: "text/plain" }));
    Object.assign(document.createElement("a"), { href: url, download: "cartas_pra_trocar.txt" }).click();
    URL.revokeObjectURL(url);
  }

  const tipos = [...new Set((data?.cartas ?? []).map((c) => c.tipo).filter(Boolean))] as string[];
  const filtradas = (data?.cartas ?? []).filter((c) => !tipo || c.tipo === tipo);

  return (
    <>
      <Cabecalho titulo="Pra trocar" subtitulo="As cartas que você tem a mais do que um deck usa" />

      <div className="mb-4">
        <Aviso tipo="info">
          Entram aqui sozinhas as cópias acima de <strong>3</strong> de cada carta, de <strong>1</strong> de cada battlefield e
          lenda e de <strong>12</strong> de cada runa. {podeEditar && "Dá pra ajustar carta por carta: trocar uma que está dentro do limite ou guardar uma que sobra."}
        </Aviso>
      </div>

      {error && <Aviso tipo="erro">{error.message}</Aviso>}
      {!data && !error && <Carregando />}

      {data && (
        <div className="space-y-4">
          <Cartao className="p-4">
            <p className="text-sm">
              <strong className="text-lg">{copias(data.copias)}</strong>
              <span className="text-apagado">
                {" "}
                de {data.cartas.length === 1 ? "1 carta" : `${data.cartas.length} cartas`}
              </span>
              {data.valor !== null && (
                <span className="text-ouro">
                  {" "}
                  · valor de referência ≈ <strong>{reais(data.valor)}</strong>
                  {data.sem_preco > 0 && <span className="text-xs text-apagado"> + {data.sem_preco} sem preço</span>}
                </span>
              )}
            </p>
            {data.valor !== null && (
              <p className="mt-1 text-xs text-apagado">Estimativa do menor preço na Liga pelo TCGplayer, a mesma do custo dos decks: serve de noção, não de preço.</p>
            )}
            {data.cartas.length > 0 && (
              <div className="mt-3 grid grid-cols-2 gap-2">
                <Botao onClick={copiar}>
                  {copiada ? <Check size={16} /> : <Copy size={16} />} {copiada ? "Copiada!" : "Copiar a lista"}
                </Botao>
                <Botao variante="secundario" onClick={baixar}>
                  <Download size={16} /> Baixar .txt
                </Botao>
              </div>
            )}
          </Cartao>

          {podeEditar && <AdicionarDaColecao naLista={new Set(data.cartas.map((c) => c.carta))} onAdicionar={(carta) => ajustar(carta, 1)} />}
          {erro && <Aviso tipo="erro">{erro}</Aviso>}

          {tipos.length > 1 && (
            <div className="sem-barra -mx-4 flex gap-2 overflow-x-auto px-4">
              <Chip ativo={!tipo} onClick={() => setTipo(null)}>
                Todas
              </Chip>
              {tipos.map((t) => (
                <Chip key={t} ativo={tipo === t} onClick={() => setTipo(tipo === t ? null : t)}>
                  {NOMES_DOS_TIPOS[t] ?? t}
                </Chip>
              ))}
            </div>
          )}

          {data.cartas.length === 0 ? (
            <p className="py-10 text-center text-sm text-apagado">Nenhuma carta sobrando: tudo o que você tem cabe nos limites de um deck.</p>
          ) : (
            <Cartao className="px-4">
              <ul className="divide-y divide-linha">
                {filtradas.map((c) => (
                  <li key={c.carta} className="flex items-center gap-3 py-3">
                    <ImagemDaCarta nome={c.carta} imagem={c.imagem} dominios={c.dominios} className="w-12 shrink-0 rounded-md" />
                    <div className="min-w-0 flex-1">
                      <NomeDaCarta carta={c.carta} className="block w-full text-sm font-medium" />
                      <p className="text-xs text-apagado">
                        tenho {c.tenho} · guardo {Math.max(0, c.tenho - c.trocar)}
                        {c.ajustado && (
                          <>
                            {" "}
                            · <span className="text-azul">ajustado</span>
                          </>
                        )}
                      </p>
                      {podeEditar && c.ajustado && (
                        <button
                          type="button"
                          onClick={() => ajustar(c.carta, null)}
                          disabled={ocupado === c.carta}
                          className="mt-0.5 inline-flex items-center gap-1 text-xs text-apagado hover:text-texto"
                        >
                          <RotateCcw size={11} /> voltar pra regra ({c.excedente === 0 ? "não sobra" : `sobram ${c.excedente}`})
                        </button>
                      )}
                    </div>
                    {podeEditar ? (
                      <div className="flex shrink-0 items-center rounded-lg border border-linha bg-superficie">
                        <button
                          type="button"
                          onClick={() => ajustar(c.carta, c.trocar - 1)}
                          disabled={ocupado === c.carta}
                          aria-label={`Trocar uma ${c.carta} a menos`}
                          className="p-2 text-apagado disabled:opacity-30"
                        >
                          <Minus size={14} />
                        </button>
                        <span className="min-w-6 text-center text-sm font-semibold text-ouro">{c.trocar}</span>
                        <button
                          type="button"
                          onClick={() => ajustar(c.carta, c.trocar + 1)}
                          disabled={ocupado === c.carta || c.trocar >= c.tenho}
                          aria-label={`Trocar uma ${c.carta} a mais`}
                          className="p-2 text-ouro disabled:opacity-30"
                        >
                          <Plus size={14} />
                        </button>
                      </div>
                    ) : (
                      <span className="shrink-0 rounded-full bg-ouro/15 px-2.5 py-1 text-xs font-semibold text-ouro">×{c.trocar}</span>
                    )}
                  </li>
                ))}
              </ul>
            </Cartao>
          )}
        </div>
      )}
    </>
  );
}

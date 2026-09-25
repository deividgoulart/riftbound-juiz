"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { ArrowLeft, Check, CheckCircle2, Copy, CopyPlus, Download, ExternalLink, Pencil, ShoppingCart, Trash2 } from "lucide-react";
import { buscar, dataCurta, pedir, reais, type DetalheDoDeck } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { ImagemDaCarta, NomeDaCarta } from "@/components/carta";
import { parametrosDaConta } from "@/components/decks";
import { FormularioDoDeck } from "@/components/formulario-deck";
import { Aviso, Botao, Cartao, Carregando, PontosDosDominios, Progresso, juntar } from "@/components/ui";

function ListaDeCompra({ d }: { d: DetalheDoDeck }) {
  const [copiada, setCopiada] = useState(false);

  async function copiar() {
    await navigator.clipboard.writeText(d.lista_de_compra);
    setCopiada(true);
    setTimeout(() => setCopiada(false), 2000);
  }

  function baixar() {
    const url = URL.createObjectURL(new Blob([d.lista_de_compra], { type: "text/plain" }));
    Object.assign(document.createElement("a"), { href: url, download: `faltam_${d.id}.txt` }).click();
    URL.revokeObjectURL(url);
  }

  return (
    <Cartao className="p-4">
      <h2 className="mb-1 flex items-center gap-2 font-semibold">
        <ShoppingCart size={17} className="text-ouro" /> Lista de compra
      </h2>
      <p className="mb-3 text-sm text-apagado">Copie e cole na Compra por Lista da Liga, que monta o carrinho mais barato entre as lojas.</p>
      <pre className="mb-3 max-h-56 overflow-auto rounded-xl border border-linha bg-fundo p-3 text-[13px] leading-relaxed">{d.lista_de_compra}</pre>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Botao onClick={copiar}>
          {copiada ? <Check size={16} /> : <Copy size={16} />} {copiada ? "Copiada!" : "Copiar"}
        </Botao>
        <a
          href={d.compra_por_lista}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-linha bg-superficie px-4 py-2.5 text-sm hover:bg-superficie-2"
        >
          <ExternalLink size={16} /> Abrir a Liga
        </a>
        <Botao variante="secundario" onClick={baixar} className="col-span-2 sm:col-span-1">
          <Download size={16} /> Baixar .txt
        </Botao>
      </div>
    </Cartao>
  );
}

export default function PaginaDoDeck() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { prefs, podeEditar } = useSessao();
  const { data: d, error, mutate } = useSWR<DetalheDoDeck>(`/api/decks/${id}?${parametrosDaConta(prefs)}`, buscar);
  const { mutate: mutarGlobal } = useSWRConfig();
  const [apagando, setApagando] = useState(false);
  const [editando, setEditando] = useState(false);
  const [ocupado, setOcupado] = useState<string | null>(null); // o que está sendo salvo agora
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  if (error) return <Aviso tipo="erro">{error.message}</Aviso>;
  if (!d) return <Carregando />;

  const doMeta = d.origem !== "manual";
  const voltar = doMeta ? "/meta" : "/decks";
  const secoes = [...new Set(d.cartas.map((c) => c.secao_nome))];

  /** Soma cópias à coleção ("já tenho" / "comprei tudo") e atualiza o deck, a coleção e as listas. */
  async function jaTenho(cartas: Record<string, number>, rotulo: string) {
    setOcupado(rotulo);
    setErro(null);
    try {
      await pedir("/api/colecao/adicionar", { method: "POST", body: JSON.stringify({ cartas }) });
      const copias = Object.values(cartas).reduce((a, b) => a + b, 0);
      setAviso(`${copias === 1 ? "1 cópia somada" : `${copias} cópias somadas`} à sua coleção.`);
      await Promise.all([mutate(), mutarGlobal((chave) => typeof chave === "string" && (chave.startsWith("/api/decks?") || chave === "/api/colecao"))]);
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setOcupado(null);
    }
  }

  async function copiar() {
    setOcupado("copiar");
    setErro(null);
    try {
      const { id: copia } = await pedir<{ id: string }>(`/api/decks/${d!.id}/copiar`, { method: "POST" });
      await mutarGlobal((chave) => typeof chave === "string" && chave.startsWith("/api/decks?"));
      router.push(`/decks/${copia}`);
    } catch (e) {
      setErro((e as Error).message);
      setOcupado(null);
    }
  }

  async function apagar() {
    if (!confirm(`Apagar o deck "${d!.nome}"?`)) return;
    setApagando(true);
    try {
      await pedir(`/api/decks/${d!.id}`, { method: "DELETE" });
      router.push("/decks");
    } catch (e) {
      setErro((e as Error).message);
      setApagando(false);
    }
  }

  return (
    <div className="space-y-4">
      <Link href={voltar} className="inline-flex items-center gap-1.5 text-sm text-apagado hover:text-texto">
        <ArrowLeft size={16} /> {doMeta ? "Decks do meta" : "Meus decks"}
      </Link>

      <Cartao className="overflow-hidden">
        <div className="flex gap-4 p-4">
          <ImagemDaCarta nome={d.lenda?.rotulo ?? d.nome} carta={d.lenda?.nome} imagem={d.lenda?.imagem} dominios={d.lenda?.dominios} className="w-24 shrink-0 sm:w-32" />
          <div className="min-w-0 flex-1">
            {d.lenda && <PontosDosDominios dominios={d.lenda.dominios} />}
            <h1 className="mt-1 font-titulo text-xl font-bold leading-tight text-ouro sm:text-2xl">{doMeta && d.lenda ? d.lenda.rotulo : d.nome}</h1>
            <p className="mt-1 text-sm text-apagado">
              {doMeta ? `${d.colocacao}º em ${d.torneio}` : d.lenda?.rotulo}
              {d.data && ` · ${dataCurta(d.data)}`}
            </p>
            {d.url && (
              <a href={d.url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 text-sm text-azul hover:underline">
                Lista original <ExternalLink size={13} />
              </a>
            )}
          </div>
        </div>
        <div className="space-y-2 border-t border-linha p-4">
          <Progresso porcentagem={d.porcentagem} />
          <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
            <span>
              <strong className="text-lg">{Math.round(d.porcentagem)}%</strong>
              <span className="text-apagado"> · tenho {d.tenho} de {d.total} cópias</span>
            </span>
            {d.cartas_faltando > 0 && d.custo !== null && (
              <span className="text-ouro">
                falta ≈ <strong className="text-lg">{reais(d.custo)}</strong>
                {d.sem_preco > 0 && <span className="text-xs text-apagado"> + {d.sem_preco} sem preço</span>}
              </span>
            )}
          </div>
        </div>
        {prefs.runas && d.cartas.some((c) => c.secao === "runas") && (
          <p className="border-t border-linha px-4 py-2 text-xs text-apagado">
            Contando as runas básicas como suas. Pra contar só as da coleção, desligue em Meus decks ou Meta.
          </p>
        )}
      </Cartao>

      {podeEditar && (
        <div className="flex flex-wrap gap-2">
          {doMeta ? (
            <Botao variante="secundario" onClick={copiar} disabled={ocupado === "copiar"}>
              <CopyPlus size={16} /> {ocupado === "copiar" ? "Copiando..." : "Copiar pros meus decks"}
            </Botao>
          ) : (
            <Botao variante="secundario" onClick={() => setEditando(true)}>
              <Pencil size={16} /> Editar
            </Botao>
          )}
        </div>
      )}
      {editando && (
        <FormularioDoDeck aberta onFechar={() => setEditando(false)} deck={d} onSalvo={() => setAviso("Deck salvo.")} />
      )}
      {aviso && <Aviso tipo="ok">{aviso}</Aviso>}

      {d.faltando.length === 0 ? (
        <Aviso tipo="ok">
          <span className="flex items-center gap-2">
            <CheckCircle2 size={18} className="text-ok" /> Você tem todas as cartas deste deck!
          </span>
        </Aviso>
      ) : (
        <>
          <Cartao className="p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <h2 className="font-semibold">
                Faltam {d.copias_faltando} cópias de {d.cartas_faltando} cartas
              </h2>
              {podeEditar && (
                <button
                  type="button"
                  disabled={!!ocupado}
                  onClick={() =>
                    confirm(`Somar as ${d.copias_faltando} cópias que faltam à sua coleção?`) &&
                    jaTenho(Object.fromEntries(d.faltando.map((c) => [c.carta, c.falta])), "tudo")
                  }
                  className="shrink-0 rounded-lg border border-ok/40 px-2.5 py-1.5 text-xs text-ok hover:bg-ok/10 disabled:opacity-50"
                >
                  {ocupado === "tudo" ? "Somando..." : "Comprei tudo"}
                </button>
              )}
            </div>
            <ul className="divide-y divide-linha">
              {d.faltando.map((c) => (
                <li key={c.carta} className="flex items-center gap-3 py-2.5">
                  <ImagemDaCarta nome={c.carta} imagem={c.imagem} className="w-10 shrink-0 rounded-md" />
                  <div className="min-w-0 flex-1">
                    <NomeDaCarta carta={c.carta} className="block w-full text-sm font-medium" />
                    <p className="text-xs text-apagado">
                      tenho {c.tem} de {c.precisa}
                    </p>
                  </div>
                  <span className="rounded-full bg-erro/15 px-2.5 py-1 text-xs font-semibold text-[#ff8a78]">−{c.falta}</span>
                  <a
                    href={c.liga}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg border border-linha px-2.5 py-1.5 text-xs text-azul hover:bg-superficie-2"
                  >
                    Liga <ExternalLink size={12} />
                  </a>
                  {podeEditar && (
                    <button
                      type="button"
                      disabled={!!ocupado}
                      onClick={() => jaTenho({ [c.carta]: c.falta }, c.carta)}
                      title={`Já tenho: somar ${c.falta} à coleção`}
                      aria-label={`Já tenho ${c.carta}: somar ${c.falta} à coleção`}
                      className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-linha text-ok hover:bg-ok/10 disabled:opacity-50"
                    >
                      {ocupado === c.carta ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-ok border-t-transparent" /> : <Check size={15} />}
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {d.legenda_dos_precos && <p className="mt-3 text-xs leading-relaxed text-apagado">{d.legenda_dos_precos}</p>}
          </Cartao>
          <ListaDeCompra d={d} />
        </>
      )}

      <Cartao className="p-4">
        <h2 className="mb-3 font-semibold">Lista completa</h2>
        <div className="space-y-4">
          {secoes.map((secao) => (
            <div key={secao}>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-apagado">{secao}</h3>
              <ul className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
                {d.cartas
                  .filter((c) => c.secao_nome === secao)
                  .map((c) => {
                    const completa = c.tem !== null && c.tem >= c.quantidade;
                    return (
                      <li key={`${c.secao}-${c.carta}`} className="flex items-center gap-2 text-sm">
                        <span className="w-6 text-right font-semibold text-ouro">{c.quantidade}</span>
                        <NomeDaCarta carta={c.carta} className={juntar("min-w-0 flex-1", c.tem !== null && !completa && "text-apagado")} />
                        {c.tem !== null && (completa ? <Check size={14} className="text-ok" /> : <span className="text-xs text-apagado">tenho {c.tem}</span>)}
                      </li>
                    );
                  })}
              </ul>
            </div>
          ))}
        </div>
      </Cartao>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {podeEditar && !doMeta && (
        <Botao variante="perigo" onClick={apagar} disabled={apagando} className="w-full">
          <Trash2 size={16} /> {apagando ? "Apagando..." : "Apagar deck"}
        </Botao>
      )}
    </div>
  );
}

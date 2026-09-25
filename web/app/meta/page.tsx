"use client";

import { useState } from "react";
import useSWR from "swr";
import { RefreshCw } from "lucide-react";
import { buscar, dataCurta, pedir, type ListaDeDecks } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { AjustesDosDecks, CartaoDoDeck, parametrosDaConta } from "@/components/decks";
import { Aviso, Botao, Cabecalho, Carregando, Chip, PontosDosDominios } from "@/components/ui";

const POR_PAGINA = 20;

export default function PaginaDoMeta() {
  const { prefs, podeEditar } = useSessao();
  const [lenda, setLenda] = useState<string | null>(null);
  const [limite, setLimite] = useState(POR_PAGINA);
  const [atualizando, setAtualizando] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);
  const chave =
    `/api/decks?tipo=meta&ordem=${prefs.ordem}&${parametrosDaConta(prefs)}&limite=${limite}` + (lenda ? `&lenda=${encodeURIComponent(lenda)}` : "");
  const { data, error, mutate } = useSWR<ListaDeDecks>(chave, buscar, { keepPreviousData: true });
  const meta = data?.meta;

  async function atualizar() {
    setAtualizando(true);
    setAviso(null);
    try {
      const r = await pedir<{ resumo: string; desconhecidas: string[] }>("/api/meta/atualizar", { method: "POST" });
      setAviso({ tipo: "ok", texto: r.resumo + (r.desconhecidas.length ? ` Cartas não reconhecidas: ${r.desconhecidas.join(", ")}.` : "") });
      mutate();
    } catch (e) {
      setAviso({ tipo: "erro", texto: (e as Error).message });
    } finally {
      setAtualizando(false);
    }
  }

  const criterio = (data?.ordem ?? prefs.ordem) === "barato" ? "mais baratos de completar" : "com menos cartas faltando";

  return (
    <>
      <Cabecalho
        titulo="Decks do meta"
        subtitulo={
          <>
            Top 8 de torneios dos últimos {meta?.dias ?? 30} dias ·{" "}
            <a href="https://topdeck.gg/riftbound" target="_blank" rel="noopener noreferrer" className="underline decoration-linha underline-offset-2">
              TopDeck.gg
            </a>
            {meta?.ultima_coleta && ` · atualizado em ${dataCurta(meta.ultima_coleta)}`}
          </>
        }
        acao={
          podeEditar &&
          meta?.chave && (
            <Botao variante="secundario" onClick={atualizar} disabled={atualizando} className="shrink-0 px-3" title="Buscar os torneios de novo">
              <RefreshCw size={16} className={atualizando ? "animate-spin" : ""} />
              <span className="hidden sm:inline">Atualizar</span>
            </Botao>
          )
        }
      />

      {meta && !meta.chave && (
        <div className="mb-4">
          <Aviso tipo="info">
            A coleta dos decks do meta está desligada: falta a TOPDECK_API_KEY (uma chave grátis da sua conta no TopDeck.gg) nos secrets da API.
          </Aviso>
        </div>
      )}
      {aviso && (
        <div className="mb-4">
          <Aviso tipo={aviso.tipo}>{aviso.texto}</Aviso>
        </div>
      )}

      {data && data.lendas.length > 0 && (
        <div className="sem-barra -mx-4 mb-4 flex gap-2 overflow-x-auto px-4">
          <Chip ativo={!lenda} onClick={() => setLenda(null)}>
            Todas as lendas
          </Chip>
          {data.lendas.map((l) => (
            <Chip key={l.nome} ativo={lenda === l.nome} onClick={() => setLenda(lenda === l.nome ? null : l.nome)}>
              <PontosDosDominios dominios={l.dominios} />
              {l.rotulo}
              <span className="text-xs opacity-60">{l.decks}</span>
            </Chip>
          ))}
        </div>
      )}

      <AjustesDosDecks temPrecos={data?.tem_precos ?? true} />
      {error && <Aviso tipo="erro">{error.message}</Aviso>}
      {!data && !error && <Carregando />}
      {data && data.total === 0 && meta?.chave && <p className="py-10 text-center text-sm text-apagado">Nenhum deck do meta ainda.</p>}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {data?.decks.map((d) => (
          <CartaoDoDeck key={d.id} d={d} />
        ))}
      </div>
      {data && data.total > 0 && (
        <div className="mt-6 space-y-3 text-center">
          <p className="text-xs text-apagado">
            Mostrando os {Math.min(limite, data.total)} {criterio} · {data.total} decks no período
          </p>
          {data.total > limite && (
            <Botao variante="secundario" onClick={() => setLimite(limite + POR_PAGINA)}>
              Ver mais {Math.min(POR_PAGINA, data.total - limite)}
            </Botao>
          )}
        </div>
      )}
    </>
  );
}

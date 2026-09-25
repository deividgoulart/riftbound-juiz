"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Plus } from "lucide-react";
import { buscar, pedir, type ListaDeDecks, type Previa } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { AjustesDosDecks, CartaoDoDeck, parametrosDaConta } from "@/components/decks";
import { Alternador, Aviso, Botao, Cabecalho, Carregando, Folha } from "@/components/ui";

const EXEMPLO = `Legend:
1 Jinx, Loose Cannon
Champion:
1 Jinx, Demolitionist
Main Deck:
3 Jinx, Rebel
...
Battlefields:
1 Altar of Blood
Runes:
6 Fury Rune
6 Chaos Rune`;

function JanelaDeImportar({ aberta, onFechar }: { aberta: boolean; onFechar: () => void }) {
  const router = useRouter();
  const [nome, setNome] = useState("");
  const [texto, setTexto] = useState("");
  const [url, setUrl] = useState("");
  const [ignorar, setIgnorar] = useState(false);
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function conferir() {
    setErro(null);
    try {
      setPrevia(await pedir<Previa>("/api/decks/previa", { method: "POST", body: JSON.stringify({ texto }) }));
    } catch (e) {
      setErro((e as Error).message);
    }
  }

  async function salvar() {
    setEnviando(true);
    setErro(null);
    try {
      const { id } = await pedir<{ id: string; avisos: string[] }>("/api/decks", {
        method: "POST",
        body: JSON.stringify({ nome, texto, url, ignorar_desconhecidas: ignorar }),
      });
      router.push(`/decks/${id}`);
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  const copias = previa?.cartas.reduce((soma, c) => soma + c.quantidade, 0) ?? 0;

  return (
    <Folha aberta={aberta} onFechar={onFechar} titulo="Importar um deck">
      <div className="space-y-3 text-sm">
        <input
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          placeholder="Nome do deck (ex.: Jinx do torneio de sábado)"
          className="w-full rounded-xl border border-linha bg-fundo px-4 py-3 outline-none focus:border-ouro"
        />
        <textarea
          value={texto}
          onChange={(e) => {
            setTexto(e.target.value);
            setPrevia(null);
          }}
          rows={9}
          placeholder={EXEMPLO}
          className="w-full rounded-xl border border-linha bg-fundo px-4 py-3 font-mono text-[13px] outline-none focus:border-ouro"
        />
        <p className="text-xs text-apagado">Cole a lista exportada pelo site de decks. Aceita &quot;3 Carta&quot;, &quot;3x Carta&quot; e &quot;Carta x3&quot;, com ou sem cabeçalhos de seção.</p>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Link da lista (opcional)"
          className="w-full rounded-xl border border-linha bg-fundo px-4 py-3 outline-none focus:border-ouro"
        />
        {previa && (
          <Aviso tipo={previa.nao_reconhecidas.length ? "alerta" : "ok"}>
            <p>
              {previa.cartas.length} cartas reconhecidas ({copias} cópias).
            </p>
            {previa.nao_reconhecidas.length > 0 && (
              <p className="mt-1">
                Não reconheci:{" "}
                {previa.nao_reconhecidas.map((n) => `"${n.texto}"${n.sugestoes.length ? ` (quis dizer ${n.sugestoes.join(" / ")}?)` : ""}`).join("; ")}
              </p>
            )}
            {previa.avisos.map((a) => (
              <p key={a} className="mt-1 text-apagado">
                Regras de construção: {a}
              </p>
            ))}
          </Aviso>
        )}
        <Alternador ligado={ignorar} onChange={setIgnorar}>
          Salvar mesmo com cartas não reconhecidas (elas ficam de fora)
        </Alternador>
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <div className="grid grid-cols-2 gap-2">
          <Botao variante="secundario" onClick={conferir} disabled={!texto.trim()}>
            Conferir
          </Botao>
          <Botao onClick={salvar} disabled={!texto.trim() || enviando}>
            {enviando ? "Salvando..." : "Salvar deck"}
          </Botao>
        </div>
      </div>
    </Folha>
  );
}

export default function PaginaDosMeusDecks() {
  const { prefs, podeEditar } = useSessao();
  const [importar, setImportar] = useState(false);
  const { data, error } = useSWR<ListaDeDecks>(`/api/decks?tipo=meus&ordem=${prefs.ordem}&${parametrosDaConta(prefs)}&limite=500`, buscar);

  return (
    <>
      <Cabecalho
        titulo="Meus decks"
        subtitulo="Os decks que você cadastrou e o que falta pra montar cada um"
        acao={
          podeEditar && (
            <Botao onClick={() => setImportar(true)} className="shrink-0 px-3">
              <Plus size={16} /> <span className="hidden sm:inline">Importar</span>
            </Botao>
          )
        }
      />
      <AjustesDosDecks temPrecos={data?.tem_precos ?? true} />
      {error && <Aviso tipo="erro">{error.message}</Aviso>}
      {!data && !error && <Carregando />}
      {data && data.decks.length === 0 && (
        <div className="rounded-2xl border border-dashed border-linha p-8 text-center text-sm text-apagado">
          Nenhum deck ainda.
          {podeEditar && (
            <div className="mt-4">
              <Botao onClick={() => setImportar(true)}>
                <Plus size={16} /> Importar um deck
              </Botao>
            </div>
          )}
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        {data?.decks.map((d) => (
          <CartaoDoDeck key={d.id} d={d} />
        ))}
      </div>
      <JanelaDeImportar aberta={importar} onFechar={() => setImportar(false)} />
    </>
  );
}

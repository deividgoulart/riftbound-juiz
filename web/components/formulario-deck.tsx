"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useSWRConfig } from "swr";
import { pedir, type Previa } from "@/lib/api";
import { Alternador, Aviso, Botao, Folha } from "./ui";

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

/** Importar um deck novo ou, com `deck`, editar um meu (nome, link e a lista, no mesmo formato de texto). */
export function FormularioDoDeck({
  aberta,
  onFechar,
  deck,
  onSalvo,
}: {
  aberta: boolean;
  onFechar: () => void;
  deck?: { id: string; nome: string; url: string | null; lista_texto: string };
  onSalvo?: () => void;
}) {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [nome, setNome] = useState(deck?.nome ?? "");
  const [texto, setTexto] = useState(deck?.lista_texto ?? "");
  const [url, setUrl] = useState(deck?.url ?? "");
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
      const corpo = JSON.stringify({ nome, texto, url, ignorar_desconhecidas: ignorar });
      const { id } = deck
        ? await pedir<{ id: string; avisos: string[] }>(`/api/decks/${deck.id}`, { method: "PUT", body: corpo })
        : await pedir<{ id: string; avisos: string[] }>("/api/decks", { method: "POST", body: corpo });
      await mutate((chave) => typeof chave === "string" && chave.startsWith("/api/decks")); // listas e detalhes
      onSalvo?.();
      onFechar();
      if (!deck) router.push(`/decks/${id}`);
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  const copias = previa?.cartas.reduce((soma, c) => soma + c.quantidade, 0) ?? 0;

  return (
    <Folha aberta={aberta} onFechar={onFechar} titulo={deck ? "Editar o deck" : "Importar um deck"}>
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
            {enviando ? "Salvando..." : deck ? "Salvar alterações" : "Salvar deck"}
          </Botao>
        </div>
      </div>
    </Folha>
  );
}


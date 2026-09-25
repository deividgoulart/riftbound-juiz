"use client";

import { useState } from "react";
import useSWR from "swr";
import { Plus } from "lucide-react";
import { buscar, type ListaDeDecks } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { AjustesDosDecks, CartaoDoDeck, parametrosDaConta } from "@/components/decks";
import { FormularioDoDeck } from "@/components/formulario-deck";
import { Aviso, Botao, Cabecalho, Carregando } from "@/components/ui";

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
      <FormularioDoDeck aberta={importar} onFechar={() => setImportar(false)} />
    </>
  );
}

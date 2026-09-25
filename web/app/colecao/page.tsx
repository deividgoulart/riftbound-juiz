"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { Download, FileUp, Minus, Plus, Search } from "lucide-react";
import { API_URL, buscar, lerToken, pedir, type Carta, type Colecao, type RelatorioCsv } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { ImagemDaCarta } from "@/components/carta";
import { Alternador, Aviso, Botao, Cabecalho, Carregando, Chip, Folha, NOMES_DOS_DOMINIOS, corDoDominio, juntar } from "@/components/ui";

const TIPOS = [
  ["Unit", "Units"],
  ["Spell", "Spells"],
  ["Gear", "Gear"],
  ["Legend", "Lendas"],
  ["Battlefield", "Battlefields"],
  ["Rune", "Runas"],
] as const;
const DOMINIOS = ["Fury", "Calm", "Mind", "Body", "Chaos", "Order"];
const POR_PAGINA = 60;

function JanelaDoCsv({ aberta, onFechar, onImportou }: { aberta: boolean; onFechar: () => void; onImportou: () => void }) {
  const { podeEditar } = useSessao();
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [substituir, setSubstituir] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [relatorio, setRelatorio] = useState<RelatorioCsv | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function exportar() {
    // O link direto não baixaria com o nome certo (a API fica em outro endereço): baixa e salva aqui.
    const resposta = await fetch(`${API_URL}/api/colecao/exportar`, { headers: lerToken() ? { Authorization: `Bearer ${lerToken()}` } : {} });
    const url = URL.createObjectURL(await resposta.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: "colecao_riftbound.csv" });
    a.click();
    URL.revokeObjectURL(url);
  }

  async function importar() {
    if (!arquivo) return;
    setEnviando(true);
    setErro(null);
    try {
      const texto = await arquivo.text();
      setRelatorio(await pedir<RelatorioCsv>("/api/colecao/importar", { method: "POST", body: JSON.stringify({ texto, substituir }) }));
      onImportou();
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Folha aberta={aberta} onFechar={onFechar} titulo="Importar ou exportar">
      <div className="space-y-4 text-sm">
        <p className="text-apagado">
          O CSV tem as colunas <strong className="text-texto">carta</strong> e <strong className="text-texto">quantidade</strong>. Também aceita direto a
          exportação de coleção da <strong className="text-texto">Liga Riftbound</strong>.
        </p>
        <Botao variante="secundario" onClick={exportar} className="w-full">
          <Download size={16} /> Baixar minha coleção (CSV)
        </Botao>
        {podeEditar && (
          <div className="space-y-3 border-t border-linha pt-4">
            <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-dashed border-linha p-4 hover:border-ouro/60">
              <FileUp size={20} className="text-ouro" />
              <span className="min-w-0 truncate">{arquivo ? arquivo.name : "Escolher arquivo CSV"}</span>
              <input type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => setArquivo(e.target.files?.[0] ?? null)} />
            </label>
            <Alternador ligado={substituir} onChange={setSubstituir}>
              Substituir a coleção inteira
              <span className="block text-xs text-apagado">Use com a exportação completa da Liga: cartas fora do arquivo saem da coleção.</span>
            </Alternador>
            <Botao onClick={importar} disabled={!arquivo || enviando} className="w-full">
              {enviando ? "Importando..." : "Importar CSV"}
            </Botao>
          </div>
        )}
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        {relatorio && (
          <Aviso tipo={relatorio.desconhecidas.length ? "alerta" : "ok"}>
            <p>
              {relatorio.importadas} cartas importadas ({relatorio.copias} cópias){relatorio.substituiu ? ", substituindo a coleção anterior." : "."}
            </p>
            {relatorio.desconhecidas.length > 0 && (
              <p className="mt-1">
                Não reconheci:{" "}
                {relatorio.desconhecidas
                  .map((d) => `"${d.texto}"${d.sugestoes.length ? ` (quis dizer ${d.sugestoes.join(" / ")}?)` : ""}`)
                  .join("; ")}
              </p>
            )}
            {relatorio.invalidas > 0 && <p className="mt-1">{relatorio.invalidas} linhas ignoradas (quantidade inválida).</p>}
          </Aviso>
        )}
      </div>
    </Folha>
  );
}

export default function PaginaDaColecao() {
  const { podeEditar, info } = useSessao();
  const { data: cartas, error: erroDasCartas } = useSWR<Carta[]>("/api/cartas", buscar, { revalidateOnFocus: false });
  const { data: colecao, mutate } = useSWR<Colecao>("/api/colecao", buscar);
  const [busca, setBusca] = useState("");
  const [tipo, setTipo] = useState<string | null>(null);
  const [dominio, setDominio] = useState<string | null>(null);
  const [soAsMinhas, setSoAsMinhas] = useState(false);
  const [mostrar, setMostrar] = useState(POR_PAGINA);
  const [mudancas, setMudancas] = useState<Record<string, number>>({});
  const [salvando, setSalvando] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);
  const [csv, setCsv] = useState(false);

  const tenho = useMemo(() => colecao?.cartas ?? {}, [colecao]);
  const quantidade = (nome: string) => mudancas[nome] ?? tenho[nome] ?? 0;

  const filtradas = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    return (cartas ?? []).filter(
      (c) =>
        (!termo || `${c.nome} ${c.tags.join(" ")}`.toLowerCase().includes(termo)) && // "jinx" acha a lenda pela tag
        (!tipo || c.tipo === tipo) &&
        (!dominio || c.dominios.includes(dominio)) &&
        (!soAsMinhas || (tenho[c.nome] ?? 0) > 0 || (mudancas[c.nome] ?? 0) > 0),
    );
  }, [cartas, busca, tipo, dominio, soAsMinhas, tenho, mudancas]);

  function mudar(nome: string, delta: number) {
    setAviso(null);
    setMudancas((m) => {
      const nova = Math.max(0, Math.min(99, (m[nome] ?? tenho[nome] ?? 0) + delta));
      const resto = { ...m };
      if (nova === (tenho[nome] ?? 0)) delete resto[nome];
      else resto[nome] = nova;
      return resto;
    });
  }

  async function salvar() {
    setSalvando(true);
    try {
      const nova = await pedir<Colecao>("/api/colecao", { method: "PUT", body: JSON.stringify({ mudancas }) });
      await mutate(nova, { revalidate: false });
      setAviso({ tipo: "ok", texto: pendentes === 1 ? "Coleção salva (1 carta alterada)." : `Coleção salva (${pendentes} cartas alteradas).` });
      setMudancas({});
    } catch (e) {
      setAviso({ tipo: "erro", texto: `Não consegui salvar: ${(e as Error).message}` });
    } finally {
      setSalvando(false);
    }
  }

  const pendentes = Object.keys(mudancas).length;

  return (
    <>
      <Cabecalho
        titulo="Minha coleção"
        subtitulo={colecao ? `${colecao.diferentes} cartas diferentes · ${colecao.copias} cópias` : "As cartas que você tem"}
        acao={
          <Botao variante="secundario" onClick={() => setCsv(true)} className="shrink-0 px-3">
            <FileUp size={16} /> <span className="hidden sm:inline">CSV</span>
          </Botao>
        }
      />

      {info?.publico && !info.turso && (
        <div className="mb-4">
          <Aviso tipo="alerta">O banco na nuvem (Turso) não está configurado: o que for salvo aqui some quando o servidor reiniciar.</Aviso>
        </div>
      )}
      {!podeEditar && info && (
        <p className="mb-4 text-xs text-apagado">Modo leitura: você vê a coleção do dono do app. Pra editar, entre com a senha (cadeado no topo).</p>
      )}

      <div className="mb-3 flex items-center gap-2 rounded-xl border border-linha bg-superficie px-3 focus-within:border-ouro/60">
        <Search size={18} className="text-apagado" />
        <input
          value={busca}
          onChange={(e) => {
            setBusca(e.target.value);
            setMostrar(POR_PAGINA);
          }}
          placeholder="Buscar pelo nome ou campeão"
          className="w-full bg-transparent py-3 text-[15px] outline-none placeholder:text-apagado/70"
        />
      </div>
      <div className="sem-barra -mx-4 mb-2 flex gap-2 overflow-x-auto px-4">
        <Chip ativo={soAsMinhas} onClick={() => setSoAsMinhas(!soAsMinhas)}>
          Só as que tenho
        </Chip>
        {TIPOS.map(([valor, rotulo]) => (
          <Chip key={valor} ativo={tipo === valor} onClick={() => setTipo(tipo === valor ? null : valor)}>
            {rotulo}
          </Chip>
        ))}
      </div>
      <div className="sem-barra -mx-4 mb-5 flex gap-2 overflow-x-auto px-4">
        {DOMINIOS.map((d) => (
          <Chip key={d} ativo={dominio === d} onClick={() => setDominio(dominio === d ? null : d)}>
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: corDoDominio(d) }} />
            {NOMES_DOS_DOMINIOS[d]}
          </Chip>
        ))}
      </div>

      {aviso && (
        <div className="mb-4">
          <Aviso tipo={aviso.tipo}>{aviso.texto}</Aviso>
        </div>
      )}
      {erroDasCartas && <Aviso tipo="erro">{erroDasCartas.message}</Aviso>}
      {!cartas && !erroDasCartas && <Carregando texto="Carregando o catálogo de cartas..." />}
      {cartas && filtradas.length === 0 && <p className="py-10 text-center text-sm text-apagado">Nenhuma carta com esses filtros.</p>}

      <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        {filtradas.slice(0, mostrar).map((c) => {
          const qtd = quantidade(c.nome);
          const mudou = c.nome in mudancas;
          return (
            <div key={c.nome} className="group">
              <div className="relative">
                <ImagemDaCarta nome={c.nome} imagem={c.imagem} dominios={c.dominios} className={juntar(qtd === 0 && "opacity-45 grayscale-[40%]")} />
                {qtd > 0 && (
                  <span
                    className={juntar(
                      "pointer-events-none absolute right-1.5 top-1.5 z-20 min-w-7 rounded-full px-2 py-0.5 text-center text-xs font-bold shadow",
                      mudou ? "bg-azul text-fundo" : "bg-ouro text-fundo",
                    )}
                  >
                    ×{qtd}
                  </span>
                )}
              </div>
              <p className="mt-1.5 line-clamp-2 min-h-8 text-xs leading-4 text-texto/90" title={c.nome}>
                {c.nome}
              </p>
              {podeEditar && (
                <div className="mt-1 flex items-center justify-between rounded-lg border border-linha bg-superficie">
                  <button type="button" onClick={() => mudar(c.nome, -1)} disabled={qtd === 0} aria-label={`Tirar uma ${c.nome}`} className="p-1.5 text-apagado disabled:opacity-30">
                    <Minus size={14} />
                  </button>
                  <span className="text-xs font-semibold">{qtd}</span>
                  <button type="button" onClick={() => mudar(c.nome, 1)} aria-label={`Pôr uma ${c.nome}`} className="p-1.5 text-ouro">
                    <Plus size={14} />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
      {filtradas.length > mostrar && (
        <div className="mt-6 text-center">
          <Botao variante="secundario" onClick={() => setMostrar(mostrar + POR_PAGINA)}>
            Mostrar mais ({filtradas.length - mostrar} cartas)
          </Botao>
        </div>
      )}

      {pendentes > 0 && (
        <div className="fixed inset-x-0 bottom-[calc(4.5rem+env(safe-area-inset-bottom))] z-30 px-4 md:bottom-6">
          <div className="mx-auto flex max-w-md items-center justify-between gap-3 rounded-2xl border border-ouro/40 bg-superficie p-3 shadow-2xl shadow-black/60">
            <span className="text-sm">{pendentes === 1 ? "1 carta alterada" : `${pendentes} cartas alteradas`}</span>
            <div className="flex gap-2">
              <Botao variante="secundario" onClick={() => setMudancas({})} className="px-3 py-2">
                Desfazer
              </Botao>
              <Botao onClick={salvar} disabled={salvando} className="px-3 py-2">
                {salvando ? "Salvando..." : "Salvar"}
              </Botao>
            </div>
          </div>
        </div>
      )}

      <JanelaDoCsv aberta={csv} onFechar={() => setCsv(false)} onImportou={() => mutate()} />
    </>
  );
}

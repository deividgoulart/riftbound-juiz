"use client";

import { useState } from "react";
import { useSessao } from "@/lib/sessao";
import { Aviso, Botao, Folha } from "./ui";

/** Janela da senha do dono: libera perguntas sem limite e a edição da coleção e dos decks. */
export function JanelaDaSenha() {
  const { pedirSenha, setPedirSenha, entrar } = useSessao();
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setErro(null);
    try {
      await entrar(senha);
      setSenha("");
      setPedirSenha(false);
    } catch (erro) {
      setErro((erro as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Folha aberta={pedirSenha} onFechar={() => setPedirSenha(false)} titulo="Entrar como dono">
      <form onSubmit={enviar} className="space-y-4">
        <p className="text-sm text-apagado">
          Com a senha, você faz perguntas sem limite e edita a coleção e os decks. O acesso fica salvo neste navegador por 30 dias.
        </p>
        <input
          type="password"
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
          placeholder="Senha"
          autoFocus
          autoComplete="current-password"
          className="w-full rounded-xl border border-linha bg-fundo px-4 py-3 outline-none focus:border-ouro"
        />
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <Botao type="submit" disabled={!senha || enviando} className="w-full">
          {enviando ? "Conferindo..." : "Entrar"}
        </Botao>
      </form>
    </Folha>
  );
}

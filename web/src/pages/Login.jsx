import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api";

export default function LoginPage() {
  const nav = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(username, password);
      nav("/");
    } catch (err) {
      setError(err.message || "خطا");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="hero-login">
      <form className="panel motion-fade" onSubmit={onSubmit}>
        <h1 className="brand">
          ماهد <span>گنجه</span>
        </h1>
        <p className="sub">ورود به پنل داخلی</p>
        <label htmlFor="u">نام کاربری</label>
        <input id="u" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        <label htmlFor="p">رمز عبور</label>
        <input
          id="p"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        <button className="primary" type="submit" disabled={loading}>
          {loading ? "…" : "ورود"}
        </button>
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  );
}

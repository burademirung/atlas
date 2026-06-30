"use strict";

(function () {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const svgNS = "http://www.w3.org/2000/svg";

  /* ── cast cards: staggered reveal on scroll ─────────────────────────── */
  const cards = document.querySelectorAll(".explain .cast-card");
  if (cards.length) {
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
        }
      },
      { threshold: 0.2 },
    );
    cards.forEach((c) => io.observe(c));
  }

  /* ── journey scrollytelling ─────────────────────────────────────────── */
  const stage = document.getElementById("stage3d");
  const steps = Array.from(document.querySelectorAll(".explain .step"));
  if (stage && steps.length) {
    const stageTilt = document.getElementById("stageTilt");
    const wires = document.getElementById("wires");
    const packet = document.getElementById("packet");
    const particles = document.getElementById("particles");
    const mock = document.getElementById("mockReport");
    const dotsWrap = document.getElementById("stepDots");
    const prevBtn = document.getElementById("prevStep");
    const nextBtn = document.getElementById("nextStep");

    // build the mock-report lines once
    if (mock) {
      const body = mock.querySelector(".mr-body");
      const widths = [100, 86, 92, 70, 96, 60];
      widths.forEach((w, i) => {
        const ln = document.createElement("span");
        ln.className = "ln" + (i === 0 ? " gold" : "");
        ln.style.width = w + "%";
        body.appendChild(ln);
      });
    }

    const STEPS = {
      1: { active: ["you"], wire: null },
      2: { active: ["you", "edge"], wire: "w-you-edge" },
      3: { active: ["edge", "claude"], wire: "w-edge-claude" },
      4: { active: ["claude"], wire: null },
      5: { active: ["claude", "web"], wire: "w-claude-web", particles: 4 },
      6: { active: ["claude", "edge", "you"], wire: "w-stream", particles: 7, stream: true },
      7: { active: ["you"], wire: null, render: true },
      8: { active: ["edge", "d1"], wire: "w-edge-d1" },
    };

    let current = 0;
    let rafId = null;

    function pathLen(id) {
      const p = document.getElementById(id);
      return p ? p.getTotalLength() : 0;
    }

    function animateAlong(el, pathId, duration, delay) {
      const path = document.getElementById(pathId);
      if (!path) return;
      const len = path.getTotalLength();
      const start = performance.now() + (delay || 0);
      el.style.opacity = "0";
      function frame(now) {
        const t = (now - start) / duration;
        if (t < 0) {
          rafId = requestAnimationFrame(frame);
          return;
        }
        if (t >= 1) {
          const pt = path.getPointAtLength(len);
          el.setAttribute("cx", pt.x);
          el.setAttribute("cy", pt.y);
          el.style.opacity = "0";
          if (el === packet) rafId = null;
          else el.remove();
          return;
        }
        // ease-in-out
        const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
        const pt = path.getPointAtLength(e * len);
        el.setAttribute("cx", pt.x);
        el.setAttribute("cy", pt.y);
        el.style.opacity = "1";
        const id = requestAnimationFrame(frame);
        if (el === packet) rafId = id;
      }
      requestAnimationFrame(frame);
    }

    function spawnParticles(pathId, count, stream) {
      if (reduce) return;
      for (let i = 0; i < count; i++) {
        const c = document.createElementNS(svgNS, "circle");
        c.setAttribute("r", stream ? "4" : "5");
        c.setAttribute("class", "flow-particle");
        particles.appendChild(c);
        animateAlong(c, pathId, stream ? 1500 : 1100, i * (stream ? 180 : 140));
      }
    }

    function setStep(n, scroll) {
      if (n === current) return;
      current = n;
      const cfg = STEPS[n];
      if (!cfg) return;
      stage.dataset.step = String(n);
      stage.setAttribute("data-active", cfg.active.join(" "));

      // dots + steps
      Array.from(dotsWrap.children).forEach((d, i) =>
        d.classList.toggle("on", i === n - 1),
      );
      steps.forEach((s) => s.classList.toggle("active", Number(s.dataset.step) === n));
      if (prevBtn) prevBtn.disabled = n <= 1;
      if (nextBtn) nextBtn.disabled = n >= steps.length;

      // mock report only on render step
      if (mock) mock.classList.toggle("show", !!cfg.render);

      // motion
      if (rafId) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
      if (!reduce && cfg.wire) {
        animateAlong(packet, cfg.wire, cfg.stream ? 1500 : 1300, 0);
        if (cfg.particles) spawnParticles(cfg.wire, cfg.particles, !!cfg.stream);
      } else {
        packet.style.opacity = "0";
      }

      if (scroll) {
        steps[n - 1].scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }

    // dots
    steps.forEach((_, i) => {
      const d = document.createElement("button");
      d.className = "d";
      d.setAttribute("aria-label", "Go to step " + (i + 1));
      d.addEventListener("click", () => setStep(i + 1, true));
      dotsWrap.appendChild(d);
    });
    if (prevBtn) prevBtn.addEventListener("click", () => setStep(Math.max(1, current - 1), true));
    if (nextBtn)
      nextBtn.addEventListener("click", () => setStep(Math.min(steps.length, current + 1), true));

    // scroll → active step (middle band)
    const stepIO = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setStep(Number(e.target.dataset.step), false);
        }
      },
      { rootMargin: "-45% 0px -45% 0px", threshold: 0 },
    );
    steps.forEach((s) => stepIO.observe(s));

    // initialise
    setStep(1, false);

    // mouse-parallax tilt
    if (!reduce && stageTilt) {
      const host = stage;
      host.addEventListener("mousemove", (ev) => {
        const r = host.getBoundingClientRect();
        const px = (ev.clientX - r.left) / r.width - 0.5;
        const py = (ev.clientY - r.top) / r.height - 0.5;
        stageTilt.style.transform = `rotateX(${(-py * 8).toFixed(2)}deg) rotateY(${(px * 9).toFixed(2)}deg)`;
      });
      host.addEventListener("mouseleave", () => {
        stageTilt.style.transform = "rotateX(0deg) rotateY(0deg)";
      });
    }

    // re-measure on resize (path lengths change with viewBox scaling? no — user units
    // are constant, but recompute defensively for the active wire)
    window.addEventListener("resize", () => void pathLen("w-stream"), { passive: true });
  }

  /* ── blueprint toggle ───────────────────────────────────────────────── */
  const bpStage = document.getElementById("bpStage");
  if (bpStage) {
    const live = document.getElementById("bp-live");
    const prod = document.getElementById("bp-prod");
    const note = document.getElementById("bpNote");
    const vLive = bpStage.querySelector(".bp-view-live");
    const vProd = bpStage.querySelector(".bp-view-prod");
    const NOTES = {
      live: "Running today: a single Cloudflare Worker, Claude Opus 4.8 searching official guidance, and a D1 database. No servers to manage.",
      prod: "The full production edition: a FastAPI backend and agent workers on Kubernetes (AWS EKS), PostgreSQL and Redis, all defined in Terraform and shipped by GitHub Actions.",
    };
    function show(view) {
      bpStage.dataset.view = view;
      const isLive = view === "live";
      live.classList.toggle("active", isLive);
      prod.classList.toggle("active", !isLive);
      live.setAttribute("aria-selected", String(isLive));
      prod.setAttribute("aria-selected", String(!isLive));
      vLive.hidden = !isLive;
      vProd.hidden = isLive;
      note.textContent = NOTES[view];
    }
    live.addEventListener("click", () => show("live"));
    prod.addEventListener("click", () => show("prod"));
  }

  /* ── tech cards: subtle 3D tilt on hover ────────────────────────────── */
  if (!reduce) {
    document.querySelectorAll(".explain .tech-card").forEach((card) => {
      card.addEventListener("mousemove", (ev) => {
        const r = card.getBoundingClientRect();
        const px = (ev.clientX - r.left) / r.width - 0.5;
        const py = (ev.clientY - r.top) / r.height - 0.5;
        card.style.transform = `perspective(700px) rotateX(${(-py * 7).toFixed(2)}deg) rotateY(${(px * 9).toFixed(2)}deg) translateY(-3px)`;
      });
      card.addEventListener("mouseleave", () => {
        card.style.transform = "";
      });
    });
  }
})();

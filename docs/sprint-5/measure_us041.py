import io, json, os, resource, statistics, time
from pathlib import Path
import django
django.setup()
from urbancheck.anonymization.service import process
from urbancheck.anonymization.tests.images import synthetic_photo

def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

def cpu_s():
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime

base_rss = rss_mb()
out = {"rss_at_start_mb": round(base_rss, 1)}
# Carga de modelos con una imagen chica.
f = io.BytesIO(synthetic_photo((320, 240))); f.name = "x.jpg"; process(f)
out["rss_after_models_mb"] = round(rss_mb(), 1)

def run(data, n):
    times, cpus = [], []
    for _ in range(n):
        f = io.BytesIO(data); f.name = "x.jpg"
        c0, t0 = cpu_s(), time.perf_counter()
        process(f)
        times.append((time.perf_counter() - t0) * 1000); cpus.append((cpu_s() - c0) * 1000)
    q = statistics.quantiles(times, n=20)[-1] if n > 1 else times[0]
    return {"mean_ms": round(statistics.fmean(times)), "p95_ms": round(q), "cpu_ms_mean": round(statistics.fmean(cpus))}

out["12mp_4000x3000"] = run(synthetic_photo((4000, 3000)), 10)
out["rss_after_12mp_mb"] = round(rss_mb(), 1)
root = Path("/app/benchmark_data/anonymization/images")
imgs = sorted(root.glob("*.jpg"))
times, cpus = [], []
for p in imgs:
    with p.open("rb") as f:
        c0, t0 = cpu_s(), time.perf_counter()
        process(f)
        times.append((time.perf_counter() - t0) * 1000); cpus.append((cpu_s() - c0) * 1000)
out["reference_set"] = {"images": len(imgs), "mean_ms": round(statistics.fmean(times)), "p95_ms": round(statistics.quantiles(times, n=20)[-1]), "cpu_ms_mean": round(statistics.fmean(cpus))}
out["peak_rss_mb"] = round(rss_mb(), 1)
out["cpus"] = os.cpu_count()
print(json.dumps(out, indent=1))

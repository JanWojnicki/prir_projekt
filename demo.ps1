param(
    [ValidateSet("demo", "shell", "test", "reproduce")]
    [string]$Mode = "demo"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Projekt C05: Entropia i segmentacja plikow binarnych (HPC)    " -ForegroundColor Cyan
Write-Host "  Autorzy: Jan Wojnicki (147020), Adrian Sajdak (146992)        " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. Sprawdzenie czy Docker Desktop dziala
$dockerOk = $false
try {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { $dockerOk = $true }
} catch {}

if (-not $dockerOk) {
    Write-Host "[!] Docker Desktop nie jest uruchomiony. Uruchamiam Docker Desktop..." -ForegroundColor Yellow
    $dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerExe) {
        Start-Process $dockerExe
        Write-Host "    Czekam na start silnika Docker (ok. 10-20 sekund)..." -ForegroundColor Yellow
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 2
            docker info *> $null
            if ($LASTEXITCODE -eq 0) {
                $dockerOk = $true
                break
            }
        }
    }
    if (-not $dockerOk) {
        Write-Error "Nie udalo sie polaczyc z Docker Desktop. Uruchom Docker Desktop recznie i sprobuj ponownie."
        exit 1
    }
}

# 2. Sprawdzenie czy obraz c05-env:latest istnieje (jesli nie, zbuduj z Dockerfile)
$imgExists = docker images -q c05-env:latest
if (-not $imgExists) {
    Write-Host "[*] Budowanie obrazu kontenera c05-env:latest z pliku Dockerfile..." -ForegroundColor Yellow
    docker build -t c05-env:latest .
}

if ($Mode -eq "shell") {
    Write-Host "[*] Otwieranie interaktywnej powloki bash w kontenerze c05-env (z dostepem do GPU)..." -ForegroundColor Green
    docker run --rm -it --gpus all --shm-size=2g -v "${ProjectRoot}:/work" -w /work c05-env:latest bash
    exit 0
}

if ($Mode -eq "test") {
    Write-Host "[*] Uruchamianie kompilacji i testow poprawnosci CTest..." -ForegroundColor Green
    docker run --rm --gpus all --shm-size=2g -v "${ProjectRoot}:/work" -w /work c05-env:latest bash -c "
        set -e
        cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
        cmake --build build -j
        ctest --test-dir build --output-on-failure -V
    "
    exit 0
}

if ($Mode -eq "reproduce") {
    Write-Host "[*] Pelne odtworzenie wszystkich eksperymentow i wykresow ze sprawozdania..." -ForegroundColor Green
    docker run --rm --gpus all --shm-size=2g -v "${ProjectRoot}:/work" -w /work c05-env:latest bash -c "
        set -e
        cmake -S . -B build -GNinja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=75 -DC05_REQUIRE_ALL=ON
        cmake --build build --parallel
        ctest --test-dir build --output-on-failure
        python3 scripts/benchmark_runner.py --build-dir build --datasets datasets --results results --generate-datasets
        python3 scripts/benchmark_cuda.py --exe build/entropy_cuda --datasets datasets --output results/cuda_benchmark.json
        python3 scripts/plot_results.py --csv results/raw_results.csv --output-dir results/plots
        python3 scripts/plot_entropy.py --csv results/segmentation.csv --events results/segmentation_events.csv --ground-truth results/ground_truth_boundaries.json --output results/plots/entropy_profile_cli.png
    "
    Write-Host "[OK] Wszystkie wyniki CSV/JSON oraz wykresy PNG/PDF zostaly odtworzone w katalogu results/!" -ForegroundColor Green
    exit 0
}

# Domyslny tryb: szybkie pokazowe uruchomienie na obronie (demo)
docker run --rm --gpus all --shm-size=2g -v "${ProjectRoot}:/work" -w /work c05-env:latest bash -c "
    set -e
    mkdir -p results/logs
    echo ''
    echo '>>> KROK 1: Kompilacja 4 wersji programu (Reference, OpenMP, MPI, CUDA)...'
    cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release >/dev/null
    cmake --build build -j

    echo ''
    echo '>>> KROK 2: Przygotowanie zbiorow danych binarnych...'
    if [ ! -f datasets/mixed_segmented.bin ]; then
        python3 scripts/generate_datasets.py --output-dir datasets --constant-mb 16 --random-mb 16 --segment-mb 8
    else
        echo 'Zbiory danych sa gotowe w katalogu datasets/.'
    fi

    echo ''
    echo '>>> KROK 3: Pokazowe uruchomienie 4 technologii (plik mixed_segmented.bin, W=4096, S=1024, T=1.0)...'
    echo '--- [1/5] Wersja referencyjna CPU (1 watek, tryb naive) ---'
    ./build/entropy_ref --input datasets/mixed_segmented.bin --window 4096 --step 1024 --threshold 1.0 --mode naive --output results/logs/demo_ref.csv --events results/logs/demo_events.csv

    echo ''
    echo '--- [2/5] Wersja OpenMP CPU (12 watkow, tryb naive) ---'
    ./build/entropy_omp --input datasets/mixed_segmented.bin --window 4096 --step 1024 --threshold 1.0 --threads 12 --mode naive --output results/logs/demo_omp_naive.csv

    echo ''
    echo '--- [3/5] Wersja OpenMP CPU (12 watkow, tryb incremental - zakres 2-osobowy) ---'
    ./build/entropy_omp --input datasets/mixed_segmented.bin --window 4096 --step 1024 --threshold 1.0 --threads 12 --mode incremental --output results/logs/demo_omp_inc.csv

    echo ''
    echo '--- [4/5] Wersja MPI (4 procesy z zakladka Halo, tryb incremental) ---'
    mpiexec --allow-run-as-root --oversubscribe -n 4 ./build/entropy_mpi --input datasets/mixed_segmented.bin --window 4096 --step 1024 --threshold 1.0 --mode incremental --output results/logs/demo_mpi.csv

    echo ''
    echo '--- [5/5] Wersja CUDA GPU (NVIDIA GTX 1660, 256 watkow/blok, Shared Memory, po rozgrzewce GPU) ---'
    ./build/entropy_cuda --input datasets/mixed_segmented.bin --window 4096 --step 1024 --threshold 1.0 --threads 256 --output results/logs/demo_cuda_warmup.csv >/dev/null 2>&1
    ./build/entropy_cuda --input datasets/mixed_segmented.bin --window 4096 --step 1024 --threshold 1.0 --threads 256 --output results/logs/demo_cuda.csv

    echo ''
    echo '>>> KROK 4: Porownanie trybu Naive vs Incremental dla malego kroku (S=64, 374 937 okien):'
    ./build/entropy_omp --input datasets/mixed_segmented.bin --window 4096 --step 64 --threshold 0.08 --threads 12 --mode naive --output results/logs/demo_s64_naive.csv
    ./build/entropy_omp --input datasets/mixed_segmented.bin --window 4096 --step 64 --threshold 0.08 --threads 12 --mode incremental --output results/logs/demo_s64_inc.csv

    echo ''
    echo '>>> KROK 5: Wykryte zdarzenia granic segmentow (results/logs/demo_events.csv):'
    cat results/logs/demo_events.csv

    echo ''
    echo '>>> KROK 6: Generowanie wykresu profilu entropii dla 8-segmentowego pliku multi_segmented.bin...'
    ./build/entropy_omp --input datasets/multi_segmented.bin --window 4096 --step 1024 --threshold 0.8 --threads 12 --mode incremental --output results/logs/segmentation_multi.csv --events results/logs/segmentation_multi_events.csv
    python3 scripts/plot_entropy.py --csv results/logs/segmentation_multi.csv --events results/logs/segmentation_multi_events.csv --ground-truth datasets/ground_truth_boundaries.json --file-key multi_segmented.bin --output results/logs/demo_entropy_profile.png
"

Write-Host ""
Write-Host "[OK] Pokaz zakonczony pomyslnie! Wykres zapisano w: results/logs/demo_entropy_profile.png" -ForegroundColor Green

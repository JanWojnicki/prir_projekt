# Projekt C05: Entropia i segmentacja plików binarnych (zespół 2-osobowy)

**Autorzy:** Jan Wojnicki (nr albumu: `147020`), Adrian Sajdak (nr albumu: `146992`)

Kompletna realizacja projektu **C05 – Entropia i segmentacja plików binarnych** obejmująca:
- **Implementację referencyjną (sekwencyjną CPU)** – [`src/reference.cpp`](src/reference.cpp), [`common/compute.cpp`](common/compute.cpp),
- **Implementację OpenMP (wielowątkową CPU)** – [`src/openmp.cpp`](src/openmp.cpp),
- **Implementację MPI (wieloprocesową z pamięcią rozproszoną / lokalną shared-memory)** – [`src/mpi.cpp`](src/mpi.cpp),
- **Implementację CUDA (GPU NVIDIA)** – [`src/cuda_entropy.cu`](src/cuda_entropy.cu),
- **Zakres zespołu 2-osobowego**: pełna implementacja i porównanie wariantu **naiwnego** (`--mode naive`, budowa histogramu od zera w każdym oknie, złożoność $\mathcal{O}(K \cdot W)$) oraz **przyrostowej aktualizacji histogramu** (`--mode incremental`, przesuwne okno z odejmowaniem $S$ opuszczających bajtów i dodawaniem $S$ wchodzących bajtów dla $S < W$, złożoność $\mathcal{O}(W + K \cdot S)$) we wszystkich czterech technologiach.

Pełne sprawozdanie z analizą algorytmiczną, metodologią, konfiguracją sprzętową, wynikami pomiarów i wykresami znajduje się w pliku **[`SPRAWOZDANIE.md`](SPRAWOZDANIE.md)**.

---

## 1. Strukturze repozytorium i udział kodu własnego

Rdzeń obliczeniowy (wyznaczanie 256-koszykowych histogramów rozkładu bajtów, obliczanie entropii Shannona w bitach na bajt z pominięciem składników o zerowym prawdopodobieństwie, przyrostowa aktualizacja histogramu, detekcja granic $|\Delta H| \ge T$ oraz scalanie sąsiednich okien przekraczających próg w pojedyncze zdarzenia zmiany) został **w całości zaimplementowany samodzielnie** w C++20 i CUDA C++. Biblioteki zewnętrzne służą wyłącznie do komunikacji i zrównoleglenia (`OpenMP`, `MPI`, `CUDA Runtime API`), obsługi standardowego wejścia/wyjścia (`STL`) oraz generowania wykresów (`matplotlib`, `seaborn`, `pandas`, `numpy`).

```text
.
├── CMakeLists.txt               # Konfiguracja budowania CMake (C++20 / OpenMP / MPI / CUDA / CTest)
├── README.md                    # Instrukcja budowania, uruchomienia i dokumentacja techniczna
├── SPRAWOZDANIE.md              # Pełne sprawozdanie projektowe (analiza, pomiary, wykresy, wnioski)
├── VALIDATION.txt               # Podsumowanie wykonanej walidacji poprawności na CPU i GPU
├── requirements.txt             # Zależności Python do analizy wyników i generowania wykresów
├── common/
│   ├── types.hpp                # Struktury danych (Options, WindowLayout, Boundary, BoundaryEvent)
│   ├── io.hpp / io.cpp          # Parser CLI, odczyt plików binarnych, zapis CSV, scalanie zmian
│   └── compute.hpp / compute.cpp# Rdzeń obliczeń: entropia Shannona, tryb naive oraz incremental
├── src/
│   ├── reference.cpp            # Wersja referencyjna jednowątkowa (naive + incremental)
│   ├── openmp.cpp               # Wersja OpenMP z prywatnymi histogramami wątków (naive + incremental)
│   ├── mpi.cpp                  # Wersja MPI z podziałem blokowym i zakładką halo (naive + incremental)
│   └── cuda_entropy.cu          # Wersja CUDA z histogramami w shared memory (naive + incremental)
├── scripts/
│   ├── generate_datasets.py     # Deterministyczny generator zbiorów testowych i ground-truth JSON
│   ├── benchmark_runner.py      # Główny skrypt pomiarowy (rozgrzewka + >=5 powtórzeń + studia dodatkowe)
│   ├── benchmark_cuda.py        # Pomocniczy skrypt szybkich pomiarów kernela CUDA (JSON)
│   ├── benchmark_all.sh         # Skrypt powłoki uruchamiający pełny potok pomiarowy
│   ├── plot_results.py          # Generator wykresów publikacyjnych (.png 300 DPI + wektorowe .pdf)
│   └── plot_entropy.py          # Samodzielny skrypt CLI rysujący wykres entropii względem pozycji z CSV
├── tests/
│   ├── check_cuda_model.py      # Model hosta weryfikujący redukcję drzewiastą, grid-stride i chunking
│   ├── verify_correctness.py    # Testy poprawności Reference + OpenMP względem wyroczni Python (144 przypadki)
│   ├── verify_mpi.py            # Testy poprawności MPI dla p=1,2,4,7 (w tym p > liczby okien) i obu trybów
│   └── verify_cuda.py           # Testy poprawności CUDA dla bloków 64..1024 i trybów naive/incremental
├── datasets/                    # Manifesty danych i dokładne pozycje granic (ground_truth_boundaries.json)
└── results/                     # Surowe wyniki pomiarów CSV, logi uruchomień, metadane i wykresy
```

---

## 2. Budowanie projektu

### Wymagania
- **CMake** $\ge 3.24$
- Kompilator **C++20** z obsługą **OpenMP** (np. `GCC 13.3`)
- Biblioteka **MPI** (np. `OpenMPI 4.1.6`)
- **NVIDIA CUDA Toolkit** $\ge 12.0$ (`nvcc`) oraz karta graficzna NVIDIA (np. `GeForce GTX 1660`, architektura Turing `sm_75`)
- **Python** $\ge 3.10$ z pakietami z `requirements.txt` (`numpy`, `pandas`, `matplotlib`, `seaborn`)

### Polecenia kompilacji
```sh
cmake -S . -B build -GNinja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=75 -DC05_REQUIRE_ALL=ON
cmake --build build --parallel
```

Opcje konfiguracyjne `CMake`:
- `-DC05_REQUIRE_ALL=ON` – wymusza obecność wszystkich włączonych technologii (OpenMP, MPI, CUDA); błąd konfiguracji w przypadku braku którejkolwiek.
- `-DC05_ENABLE_OPENMP=ON|OFF`, `-DC05_ENABLE_MPI=ON|OFF`, `-DC05_ENABLE_CUDA=ON|OFF` – włączanie/wyłączanie poszczególnych backendów.
- `-DC05_NATIVE=ON|OFF` – domyślnie włącza `-march=native` dla kompilatora hosta.
- `-DCMAKE_CUDA_ARCHITECTURES=75` (lub `native`) – docelowa architektura GPU (nie używamy `--use_fast_math`, aby zachować pełną dokładność `double` IEEE-754).

---

## 3. Interfejs wiersza poleceń (CLI) i uruchomienie

Wszystkie cztery pliki wykonywalne (`entropy_ref`, `entropy_omp`, `entropy_mpi`, `entropy_cuda`) przyjmują identyczny, ujednolicony zestaw argumentów:

```sh
./build/entropy_ref  --input PLIK --window W --step S --threshold T --output WYNIK.csv [--events ZMIANY.csv] [--mode naive|incremental]
./build/entropy_omp  --input PLIK --window W --step S --threshold T --output WYNIK.csv [--events ZMIANY.csv] [--threads N] [--mode naive|incremental]
mpiexec -n P ./build/entropy_mpi --input PLIK --window W --step S --threshold T --output WYNIK.csv [--events ZMIANY.csv] [--mode naive|incremental]
./build/entropy_cuda --input PLIK --window W --step S --threshold T --output WYNIK.csv [--events ZMIANY.csv] [--threads BLOK] [--mode naive|incremental]
```

### Opis parametrów CLI
- `--input FILE` – ścieżka do wejściowego pliku binarnego.
- `--window W` – długość okna w bajtach ($1 \le W \le 2^{32}-1$).
- `--step S` – krok przesunięcia okna w bajtach ($S \ge 1$). Dla $S < W$ sąsiednie okna nakładają się na siebie; dla $S > W$ powstają niepokryte przerwy raportowane na `stderr`.
- `--threshold T` – nieujemny próg zmiany entropii w bitach na bajt ($T \ge 0$). Okno $i \ge 1$ otrzymuje flagę granicy (`is_boundary = 1`) wtedy i tylko wtedy, gdy $|H_i - H_{i-1}| \ge T$.
- `--output CSV` – plik wyjściowy CSV dla wszystkich pełnych okien (`offset,entropy,delta,is_boundary`).
- `--events CSV` – *(opcjonalnie)* plik wyjściowy CSV zawierający **listę scalonych zmian** (`event,first_window,last_window,region_start,region_end,estimated_offset,peak_window,peak_delta,entropy_before,entropy_after,net_delta`). Ciąg kolejnych okien przekraczających próg na jednej fizycznej granicy segmentów jest łączony w pojedyncze zdarzenie zmiany ze środkiem przedziału `estimated_offset`.
- `--threads N` – dla OpenMP: liczba wątków roboczych; dla CUDA: liczba wątków w bloku (`64, 128, 256, 512, 1024`, domyślnie `256`).
- `--mode naive|incremental` – wybór algorytmu wyznaczania histogramu:
  - `naive` – pełne zliczanie $W$ bajtów w każdym oknie niezależnie,
  - `incremental` – aktualizacja przyrostowa przesuwnego histogramu (odjęcie $S$ bajtów opuszczających okno i dodanie $S$ bajtów wchodzących do okna dla $S < W$).

### Obsługa niepełnego okna końcowego
Przetwarzane są wyłącznie pełne okna mieszczące się w pliku:
- Dla $N < W$ liczba okien wynosi $K = 0$ (tworzony jest plik CSV z samym nagłówkiem).
- Dla $N \ge W$ liczba okien wynosi $K = 1 + \lfloor (N - W) / S \rfloor$.
- Liczba pominiętych bajtów na końcu pliku (`omitted_trailing_bytes`) oraz ewentualnych bajtów w przerwach dla $S > W$ (`uncovered_gap_bytes`) jest zawsze jawnie raportowana na `stderr`.

### Samodzielne generowanie wykresu entropii względem pozycji
```sh
python3 scripts/plot_entropy.py \
  --csv results/segmentation.csv \
  --events results/segmentation_events.csv \
  --ground-truth results/ground_truth_boundaries.json \
  --output entropy_profile.png
```

---

## 4. Testy poprawności

Pełny zestaw testów automatycznych uruchamiany jest przez `CTest`:
```sh
ctest --test-dir build --output-on-failure
```

Zestaw obejmuje 4 grupy testów:
1. `host_model_correctness` ([`tests/check_cuda_model.py`](tests/check_cuda_model.py)) – 500 losowych modeli redukcji drzewiastej w pamięci współdzielonej dla bloków `64..1024`, pełne pokrycie pętli `grid-stride` oraz model arytmetyki modularnej `uint32_t` przy przeplocie `atomicSub`/`atomicAdd` w trybie przyrostowym.
2. `reference_and_openmp_correctness` ([`tests/verify_correctness.py`](tests/verify_correctness.py)) – 144 kombinacje przypadków brzegowych (pusty plik, $N < W$, $W = 1$, $S < W$, $S = W$, $S > W$, progi $0.0, 0.1, 8.0$) porównujące `Ref-Naive`, `Ref-Incremental`, `OMP-Naive` i `OMP-Incremental` (dla 1, 2 i 4 wątków) z niezależną wyrocznią w Pythonie, test progu włącznego $|\Delta H| = T$, weryfikację pliku `--events` oraz odrzucanie błędnych argumentów CLI.
3. `mpi_correctness` ([`tests/verify_mpi.py`](tests/verify_mpi.py)) – 128 konfiguracji porównujących `MPI-Naive` i `MPI-Incremental` dla liczby procesów $p \in \{1, 2, 4, 7\}$ (w tym przypadek $p > K$, gdzie część procesów otrzymuje 0 okien) z implementacją referencyjną.
4. `cuda_correctness` ([`tests/verify_cuda.py`](tests/verify_cuda.py)) – 112 konfiguracji na fizycznym GPU porównujących `CUDA-Naive` i `CUDA-Incremental` dla wszystkich rozmiarów bloku (`64, 128, 256, 512, 1024`) z referencją CPU при rygorystycznej tolerancji $\varepsilon = 10^{-6}$ (rzeczywisty maksymalny błąd na GPU wynosi $3{,}55 \times 10^{-15}$).

---

## 5. Generowanie danych, pomiary i wykresy

Wygenerowanie deterministycznych zbiorów danych (`seed = 2026`), wykonanie pełnej sesji pomiarowej (1 rozgrzewka + 5 niezależnych pomiarów każdej konfiguracji w losowej kolejności + eksperymenty dodatkowe) oraz wygenerowanie wykresów `.png` i `.pdf`:

```sh
python3 scripts/benchmark_runner.py --build-dir build --datasets datasets --results results --generate-datasets
python3 scripts/benchmark_cuda.py --exe build/entropy_cuda --datasets datasets --output results/cuda_benchmark.json
```

Aby ponownie wygenerować same wykresy z istniejących surowych pomiarów `results/raw_results.csv`:
```sh
python3 scripts/plot_results.py --csv results/raw_results.csv --output-dir results/plots
```

---

## 6. Podział pracy w zespole 2-osobowym

- **Jan Wojnicki (nr albumu: 147020) – Zakres podstawowy + OpenMP + CUDA Naive + Infrastruktura danych i testów:**
  - Wspólny moduł `common/` (CLI, I/O, pełne okna, detekcja granic, wyjście CSV),
  - Implementacja referencyjna w trybie naiwnym (`compute_naive`) oraz zrównoleglenie OpenMP (`OMP-Naive` z prywatnymi histogramami wątków),
  - Implementacja kernela `histogram_entropy_kernel` (`CUDA-Naive`) i `boundary_flags_kernel` z redukcją drzewiastą w `shared memory`,
  - Generator zbiorów syntetycznych (`generate_datasets.py`) oraz testy poprawności (`verify_correctness.py`, `verify_cuda.py`).
- **Adrian Sajdak (nr albumu: 146992) – Rozszerzenie 2-osobowe: Wariant przyrostowy + MPI + Badania eksperymentalne i wizualizacja:**
  - Opracowanie i implementacja przyrostowej aktualizacji histogramu (`--mode incremental`) w wersji referencyjnej (`compute_incremental`), OpenMP (`OMP-Incremental` z podziałem pasmowym), MPI (`MPI-Incremental`) oraz CUDA (`incremental_entropy_kernel` z aktualizacją `atomicSub`/`atomicAdd` na pasmach okien),
  - Implementacja wersji MPI (`src/mpi.cpp`) z nieblokującą dystrybucją zakładki (`MPI_Isend`/`MPI_Recv`), synchronizacją pomiarów i zbieraniem wyników (`MPI_Gatherv`),
  - Scalanie sąsiednich przekroczeń progu w pojedyncze zdarzenia zmian (`BoundaryEvent`, `--events`), testy `verify_mpi.py`, skrypty pomiarowe i wykresy (`benchmark_runner.py`, `plot_results.py`, `plot_entropy.py`).

Obaj autorzy uczestniczyli w przeglądzie kodu, walidacji wyników i przygotowaniu sprawozdania oraz rozumieją całość rozwiązania.

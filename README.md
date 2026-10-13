# C05: Krok 3, CUDA

Kompletna paczka zgodna z modulem common z kroku 1. Nie nadpisuje ani nie
udaje zmian kroku 2: dolaczone CPU/OpenMP/MPI pochodza z kroku 1. Aby zachowac
wlasne zmiany kroku 2, przenies tylko src/cuda_entropy.cu, nowe skrypty/testy
oraz zmiany celu CUDA w CMakeLists.txt. Nie kompiluj jednoczesnie starego
src/cuda.cu i nowego pliku: oba zawieraja main().

## Budowanie

Wymagania: CMake >=3.24, C++20, CUDA toolkit z obsluga C++20 i zgodny
kompilator hosta, sterownik i GPU NVIDIA do uruchomienia. Skrypty: Python >=3.9.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=75 -DC05_REQUIRE_ALL=ON
cmake --build build --parallel
```

Na maszynie bez MPI mozna uzyc -DC05_ENABLE_MPI=OFF. C05_REQUIRE_ALL=ON
wymusza dostepnosc wszystkich wlaczonych backendow. Bez tej opcji niedostepne
backendy sa jawnie pomijane. Na maszynie z widocznym GPU mozna uzyc
-DCMAKE_CUDA_ARCHITECTURES=native zamiast 75. -march=native jest domyslne;
-DC05_NATIVE=OFF pozwala uniknac zaleznosci binarium od CPU kompilujacego.
Nie uzywamy --use_fast_math. CUDA kompilowana z -lineinfo do profilowania.

## Uruchomienie

```sh
python3 scripts/generate_datasets.py --output-dir datasets
./build/entropy_cuda --input datasets/mixed_segmented.bin --window 65536 --step 8192 --threshold 0.1 --output cuda.csv --threads 256 --mode naive
./build/entropy_ref --input datasets/mixed_segmented.bin --window 65536 --step 8192 --threshold 0.1 --output ref.csv --mode naive
python3 tests/verify_correctness.py --ref-csv ref.csv --inc-csv cuda.csv
python3 tests/verify_cuda.py --ref-exe ./build/entropy_ref --cuda-exe ./build/entropy_cuda
ctest --test-dir build --output-on-failure
```

Test CUDA wymaga rzeczywistego GPU, nie ma CPU fallback. CTest rejestruje test
CUDA tylko gdy cel entropy_cuda istnieje; etykieta testu to gpu. Na wezle
kompilujacym bez GPU uruchamiaj tylko test CPU przez ctest -R '^reference_correctness$'. Test GPU sprawdza 240 kombinacji oraz
rownosc progu, max blad <1e-6 i identyczne flagi. Test obejmuje 64/128/256/512
watkow na blok; 1024 jest dopuszczalne, ale nie jest czescia tej macierzy.

--threads dla CUDA oznacza watki na blok: 64,128,256,512,1024; domyslnie 256.
Limit GPU jest sprawdzany. --mode naive oznacza shared atomic histogram;
--mode incremental jest odrzucane. W i S musza byc dodatnie; W <= UINT32_MAX.
N<W i pusty plik daja CSV z samym naglowkiem bez uruchamiania CUDA.

## Architektura

histogram_entropy_kernel: blok liczy okno, s_hist[256] unsigned int,
zerowanie i bariery, atomicAdd dla kazdego bajtu, 256 skladnikow double,
redukcja drzewiasta w shared memory. Grid-stride obsluguje wiecej okien niz
limit wymiaru siatki. Kazdy blok moze liczyc kolejne okna, resetujac histogram.
Zaden blok nie wspoldzieli histogramu z innym blokiem. Wszystkie watki bloku
wykonuja kazda bariere. Redukcja dziala takze dla blokow mniejszych niz 256.

boundary_flags_kernel: grid-stride po indeksach okien, fabs(delta)>=threshold,
flagi uint8_t. Pierwsza flaga zawsze 0, takze dla threshold=0. Nie ma
kompaktowania indeksow ani atomicAdd do globalnego licznika granic. CPU
buduje uporzadkowane struktury Boundary z flag GPU po D2H. CSV zapisuje
rzeczywiste flagi GPU, nie zastepuje ich ponowna detekcja na CPU. CPU dodatkowo
sprawdza spojnosc flag z przeslanymi entropiami i odrzuca NaN/Inf.

Offset granicy to poczatek aktualnego okna, nie gwarantowana fizyczna granica
segmentu. Delta jest podpisana. Tylko pelne okna: K=0 gdy N<W, inaczej
K=1+(N-W)/S. stderr raportuje bajty za ostatnim pelnym oknem oraz osobno
niepokryte przerwy dla S>W. Wyniki sa zgodne ze schematem kroku 1.

## Pomiary

Kazda faza GPU ma eventStart/eventStop i timer steady_clock. Przed faza jest
cudaDeviceSynchronize(); stop event jest kolejkowany po operacji, nastepnie
cudaDeviceSynchronize() i odczyt zakonczonego pomiaru. Kolejkowanie stop event
po synchronizacji hosta dodawaloby bezczynny odstep do pomiaru kernela.

- T_H2D_wall_s / T_H2D_event_s: transfer calego pliku.
- T_entropy_kernel_wall_s / T_entropy_kernel_event_s: histogram + entropia.
- T_boundary_kernel_wall_s / T_boundary_kernel_event_s: flagi granic.
- T_D2H_wall_s / T_D2H_event_s: entropie oraz flagi.
- T_postprocess_cpu_s: kontrola wynikow i utworzenie wektora Boundary.
- T_write_csv_s: zapis, flush i close; bez gwarancji fsync.
- T_read_s, T_setup_s, T_cleanup_s: osobne koszty wejscia i zasobow CUDA.
- T_core_s: histogram + entropia (events), zgodnie z CPU z kroku 1.
- T_gpu_compute_s: suma czasow events OBU kerneli; bez transferow i CPU.
- T_total_s: od wczytania do zamkniecia CSV, z alokacjami, komunikacja,
  synchronizacjami, sprzataniem zasobow CUDA i postprocessingiem.

T_core_s = T_entropy_kernel_event_s, co zachowuje porownywalnosc z CPU
z kroku 1. Kernel granic jest raportowany osobno i w T_gpu_compute_s.
Nie sumuj wall i event: sa to dwa widoki tej samej fazy. T_total obejmuje
rowniez narzut timerow, alokacje wektorow i operacje poza nazwanymi fazami.

Host uzywa pageable std::vector. Wall transferow jest pomiarem end-to-end,
events sa pomocniczym pomiarem odstepu na strumieniu, NIE czystego czasu DMA.
Pageable staging i przerwy hosta moga wplywac na ten odstep. Program nie
naklada transferow i obliczen. Pojedynczy przebieg nie ma rozgrzewki kernela.

## Badanie atomics

256 koszykow histogramu NIE oznacza 256 bankow shared memory. Dla typowych
wspolczesnych GPU shared memory ma 32 banki; wiele koszykow trafia do jednego
banku. Konflikt banku i kolizja atomic na tym samym adresie sa roznymi
zjawiskami. Dla zer wszystkie aktualizacje w bloku trafiaja do s_hist[0].
Dla uniform random aktualizacje sa statystycznie rozlozone na 256 koszykow,
lecz nadal moga kolidowac. Nie zakladamy braku kolizji ani gwarantowanego
przyspieszenia bez pomiarow.

```sh
python3 scripts/benchmark_cuda.py --exe ./build/entropy_cuda --datasets datasets --window 65536 --step 65536 --threads 256 --repeats 5 --output cuda_benchmark.json
ncu --set full --kernel-name regex:histogram_entropy_kernel -o zeros ./build/entropy_cuda --input datasets/constant_bytes.bin --window 65536 --step 65536 --threshold 0.1 --output zeros.csv --threads 256
ncu --set full --kernel-name regex:histogram_entropy_kernel -o random ./build/entropy_cuda --input datasets/uniform_random.bin --window 65536 --step 65536 --threshold 0.1 --output random.csv --threads 256
```

Benchmark uruchamia osobne procesy, odrzuca pierwszy przebieg na kazdym
zestawie i zapisuje surowe wyniki oraz mediany. Nie jest to rozgrzewka kernela
w jednym kontekscie CUDA. Dla porownania atomics utrzymuj te same W/S/blok,
GPU, ustawienia zegarow i obciazenie. Zera i uniform maja ten sam rozmiar.
Czas kernela obejmuje rowniez log2 i redukcje: NIE jest izolowanym czasem
atomicAdd. Dane stale maja mniej niezerowych skladnikow log2; profiler pomaga
odroznic ten efekt od contention. ncu moze replayowac kernel i zmieniac czasy:
nie uzywaj czasow aplikacji spod profilera jako zwyklego benchmarku.

logical_histogram_GBps = K*W / T_entropy_kernel_event_s / 1e9.
To przepustowosc logicznych bajtow okien, NIE rzeczywista przepustowosc DRAM;
nakladajace sie okna i cache moga dac wartosci wieksze od przepustowosci DRAM.
Program wymaga calego pliku i wynikow w RAM/VRAM, nie jest out-of-core.

## Dokladnosc i walidacja

Redukcja GPU ma inna kolejnosc dodawania niz CPU. Wymagamy bledu <1e-6,
ale bliskosc progu do rzeczywistego delta moze zmienic flage mimo malego bledu.
Nie dodajemy epsilon do reguly detekcji; test porownania flag pozostaje scisly.

W srodowisku dostawy brak nvcc, GPU i CMake. Kompilacja/uruchomienie CUDA oraz
profilowanie NIE zostaly wykonane. Zweryfikowano skladnie skryptow, regresje
CPU/OpenMP i indeksowanie/redukcje na modelu hosta; to nie zastepuje testu GPU.
CHECK_CUDA obsluguje bledy API, launch i asynchroniczne bledy synchronizacji.
Zasoby maja RAII; normalne zwalnianie jest sprawdzane, destruktory przy
wyjatku raportuja bledy bez rzucania kolejnego wyjatku.

## Dokumentacja zrodlowa

- [CUDA Best Practices](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html)
- [CUDA API synchronization](https://docs.nvidia.com/cuda/cuda-runtime-api/api-sync-behavior.html)
- [Shared atomic histograms](https://developer.nvidia.com/blog/gpu-pro-tip-fast-histograms-using-shared-atomics-maxwell/)
- [Nsight Compute CLI](https://docs.nvidia.com/nsight-compute/NsightComputeCli/index.html)

# ADASLab

ADASLab, Python + PySide6 / Qt Quick masaüstü uygulamasıdır; kaynakları bu `DeviceStudio` klasöründedir. Gerçek 3B sürüş, firmware yükleme, DeviceBoot yönetimi, Düello kontrolü ve komut konsolu aynı penceredir. ADAS kararları saatteki C firmware'inde çalışır.

## Açılış

Python 3.12+ gerekir. Başlatıcılar proje içindeki `.venv` ortamını hazırlar; bağımlılıklar `requirements.txt` içinde sabitlenmiştir (`PySide6==6.12.0`, `pyserial==3.5`).

```sh
# macOS
./Start.command
# Windows / PowerShell
./Start.ps1
# Hazır Python ortamıyla (Windows: .venv\Scripts\python.exe studio.py)
.venv/bin/python studio.py
```

ADASLab sürüş sayfasıyla açılır ve seçili ST-LINK seri portuna otomatik bağlanır. Sol menünün ilk öğesi **ADASLab**'dır; **Firmware**, **Düello** ve **Komut konsolu** aynı listededir, üstte **Device Studio** başlığı durur. USB sonradan takıldıysa üstteki yenile düğmesiyle portları taratıp **Bağlan** seçin. `--game` de aynı Studio görünümünü açar. `--game-sim` fiziksel karta erişmeden derlenmiş ARM firmware'ini kullanır. Eski `--adas` / `--game-2d` seçenekleri bu yeni görünüme uyumluluk takma adıdır; eski ekranları açmaz.

## Saatten başlat, Studio'da oyna

Kartta **ADASLab v3 (ID 3)** ve DeviceBoot v2 bulunmalıdır. Kör nokta, şerit takip ve yan/arka çarpışma önleme kararları kartta verildiği için sürüş v3 ister; kartta eski sürüm varsa güncel `Firmware/ADASLab.dfw` paketini yükleyin. Masaüstündeki yalnız grafik değişiklikleri için firmware yeniden yüklenmez.

1. Saati ST-LINK USB bağlantısıyla bağlayın, ADASLab'ı açın ve sürüş görünümünü etkin bırakın.
2. Giriş ekranındaki kartın **Aracını seç** bölümünden **Tofaş Şahin**, **Tesla Model 3** veya uçan **Tesla Taklacı Güvercin Serisi**'ni seçin. Seçilen araç vitrinde gösterilir, sürüşte kullanılır ve sonraki açılışta hatırlanır.
3. Saatten **AKTİF / UYARI / KAPALI**, **ACC**, hedef hız **− / +** ve **TAKİP** ayarını seçin. Studio'nun üst göstergeleri bu değerleri salt okunur gösterir.
4. Studio'daki **BAŞLAT** düğmesine veya saatteki **BAŞLAT**'a dokunun. Oyun Studio'nun içindeki 3B sahnede başlar ve klavye odağı otomatik yola geçer.
5. **W / ↑** gaz, **S / ↓ / Boşluk** fren, **A–D / ← →** direksiyon, **Q / E** sol/sağ sinyaldir. Pedallar gerçek ayak gibi kademeli basılır (gaz 0,25 s, fren 0,25 s). Direksiyon tuş basılı kaldıkça döner, bırakınca merkeze gelir ve araç olduğu yerde kalır: şeridin ortasından, sağından veya solundan gidebilirsiniz. Sinyal bir basışla açılır; aynı tuş veya yeni şeride tam girmek onu kapatır. **C** takip/pilot kamerasını, **V** yol çizimlerini (takip koridoru, araç çerçevesi, kör nokta), **M** sesi açıp kapatır.
6. **Esc**, Studio'daki **DURAKLAT** veya saatteki **DURAKLAT** sürüşü duraklatır. Studio'daki **DEVAM ET** veya saatteki **BAŞLAT** aynı yolu sürdürür; **YENİDEN BAŞLAT · ARAÇ SEÇ** duraklatılan yolu bırakıp araç seçimine döner, çarpışmayı beklemek gerekmez. Hangisinden yapılırsa yapılsın iki ekran aynı durumu gösterir. Çarpışma veya 120 simülasyon saniyesi sonunda sonraki başlatma (Studio'da **YENİ SÜRÜŞ**) yeni sürüş hazırlar.

Sol alttaki gösterge paneli hızı, ACC hedef hız işaretini, ACC/FCW/AEB uyarı lambalarını, sinyal oklarını, takip süresini ve gaz/fren ivmesini gösterir. Sağ alttaki **Sensör görünümü** önde 110 m, arkada daha sıkışık ölçekle 60 m içindeki araçları şeritleriyle çizer; öndeki araç vurgulanır, kör noktadaki ve arkadan gelen izlenen araç sarı olur, takip mesafesi, TTC ve bağıl hız altında yazar. 3B sahnede öndeki araç ADAS kamera çerçevesiyle işaretlenir (**araç çerçevesi**); ego şeridindeki **takip koridoru** hıza göre gereken takip mesafesini gösterir ve öndeki araç bu mesafeye girince sarıya, AEB'de kırmızıya döner. Yolun altındaki **GÖSTERGELER** sırası bunları (**Koridor**, **Çerçeve**, **Kör nokta**, **Sensör**) ayrı ayrı açıp kapatır; sürüş sırasında da kullanılabilir, seçim sonraki açılışta hatırlanır. Saatte ADAS KAPALI seçiliyken yol çizimleri zaten görünmez. Sarı **ÇARPIŞMA UYARISI** FCW'yi, kırmızı **AEB · ACİL FREN** gerçek firmware'in acil fren isteğini ekran kenarı uyarısı ve sesli uyarıyla gösterir. Sürüş bitince puan, mesafe, uyarı, AEB müdahalesi, ramak kala ve ortalama tepki süresi özetlenir. ACC açıkken pedallara basmazsanız hedef hız ve takip süresini saat yönetir. Mod ve durum kart ekranında da izlenebilir.

### Kör nokta, şerit takip ve yan/arka çarpışma önleme

Bu kararların hepsi kartta C ile verilir ([ADASLab/src/surround.c](../ADASLab/src/surround.c)); Studio yalnız sensörleri `N:` ile gönderir, gelen isteği araca uygular ve gösterir. Değerler eğitim kalibrasyonudur, gerçek araç için doğrulanmamıştır; her çarpışmanın önleneceği garanti edilmez.

- **Kör nokta:** Yan bant 3,5 m; bölge aynadan arka tamponun 3 m gerisine kadardır, 3,5 s içinde bölgeye girecek araç da sayılır. Araç varsa lamba sarı, o tarafa sinyal verir veya direksiyon kırarsanız kırmızıdır ve ses çıkar. Araç yan bölgedeyken üstüne kırmak karşı direksiyonla engellenir, bu müdahale aşılamaz.
- **Şerit takip:** Sinyalsiz çizgiye yaklaşınca kart direksiyonla geri iter. Direksiyonu yaklaşık 1 s zorlarsanız bırakır (**SÜRÜCÜ DEVRALDI**) ve şerit değiştirirsiniz. Zorlamayı 0,3 s bırakırsanız aracı en yakın şeride alır. O tarafa sinyal verilince hiç karışmaz. 30 km/sa altında ve öndeki tehlikeden kaçarken direnmez.
- **Yandan gelen araç:** Yanınızda bir araç 1 s içinde gövdeye değecekse diğer taraf boşsa uzaklaştırır; araç arkadaysa gaz, öndeyse fren ile yolunu açar.
- **Arkadan gelen araç:** 3,5 s altında uyarır. 2 s altında ve yavaşlamıyorsa ön yol boşken gaza basar (ACC sınırı olan 2 m/s²'yi aşarak, aracın gücü kadar). Ön doluysa veya 1,2 s altına inmişse boş şeride kaçar; her yer doluysa yalnız uyarır. Sürücünün freni gazı iptal eder; AEB her zaman önceliklidir. Gaz her araçta aynı işe yaramaz: 100 km/sa'te Şahin yaklaşık 1, Model 3 yaklaşık 5 m/s² ivmelenir, Şahin'de asıl kurtuluş şerit değiştirmektir.
- **Modlar:** **Yalnız uyarı** lambaları ve uyarıları gösterir, direksiyon ve pedallara dokunmaz. **ADAS kapalı** hiçbir şey yapmaz.

**Pilot kamerada** direksiyon simidi, gösterge paneli ve iki gerçek görüntülü yan ayna vardır; yandaki araç aynadan çıktığı halde lambanın yanmaya devam etmesi kör noktayı gösterir. **Takip kamerasında** aracın iki yanında yola silik bölgeler çizilir, doluyken sarı, riskte kırmızı olur; altta küçük direksiyon ve SOL/SAĞ lambaları durur. Kart ekranında hızın iki yanındaki lambalar ve durum satırı aynı bilgiyi verir.

### Gerçek dünya fiziği

Araçlar yayımlanmış verilerle sürülür (sürücü 75 kg dahil): **Tofaş Şahin 1.6** 59 kW / 126 N·m, beş ileri düz vites (0,5 s'lik vites boşlukları, gaz köklenince vites düşürme), arkadan itiş, ABS'siz 7,4 m/s² fren; 0–100 km/sa ≈12,5 s, en fazla ≈165 km/sa. **Tesla Model 3 Long Range AWD** 0–100 km/sa 4,5 s, 201 km/sa sınırlı, ≈10 m/s² fren, ayak gazdan çekilince tek pedal rejeneratif fren (≈1,3 m/s²; 1,3 m/s² üstünde stop lambası yanar, UN R13‑H). **Taklacı Güvercin** fanlarla yola basar: 0–60 mph 1,55 s (yalnız lastikle), 1,5 g fren. Hepsinde aerodinamik sürtünme, yuvarlanma direnci, motor/tahrik gecikmesi ve 0,12 s fren basıncı gecikmesi hesaplanır; kart protokolü 216 km/sa ile sınırlı olduğundan bu hızın üstüne çıkılmaz.

Direksiyon, basılı tuşla 0,45 s'de tam kilide gelir, bırakılınca 0,25 s'de döner. En fazla 2,8 m/s² yanal ivme ister (≈2,5–3 s'de bir şerit); öndeki araca TTC < 3 s ise lastik tutuşunun %60'ı kullanılır. Direksiyon dönünce aracın yönü 0,7 s içinde yola hizalanır ve araç olduğu yerde kalır; kısa dokunuş yaklaşık 20 cm kaydırır. Otomatik ortalama yoktur. Yanal hız aracın hızıyla sınırlıdır: duran araç yana kaymaz. Yol, orta bariyer ile sağ korkuluk arasındadır; emniyet şeridinde gidilebilir, bariyere sürtmek aracı 3 m/s² yavaşlatır ve puan düşürür, sürüşü bitirmez.

Trafik, Intelligent Driver Model (IDM) ile takip eder ve MOBIL ile şerit değiştirir: sürücülerin istenen hızı şeride göre (sol 105, orta 90, sağ 75 km/sa ortalamalı), takip süresi 1,0–2,0 s, konfor freni ≈2 m/s², acil fren en çok 9 m/s². Şerit değiştirmeden önce 1–2,5 s sinyal verirler (%15'i vermez), hiçbir arkadaki aracı 4 m/s²'den sert frene zorlamazlar ve sağ şeridi tercih ederler. Oyuncu da trafiğin parçasıdır: önüne giren oyuncu için arkadaki araç fren yapar, yavaş giden oyuncuyu arkadan gelenler geçer. Trafikte en çok 16 araç olur ve ara sıra biri hafifçe yavaşlar. 5–11 s'de bir arkadan, oyuncunun o anki hızına göre 15–30 veya 30–60 km/sa daha hızlı bir araç gelir. Bazıları kör nokta ve arka önlemeyi sınar: yaklaşık her on ikincisi aynı şeritte dalgındır ve oyuncuyu ancak çarpmaya 1–1,5 s kala görür; 20–30 s'de bir yandaki bir sürücü bakmadan önünüze kırar. Bunlar yalnız oyuncuya karşı dikkatsizdir, birbirlerine çarpmazlar. Aynı tohum ve aynı girdilerle hepsi aynı şekilde tekrarlanır. Araç sınıfları gerçek boyutlarıyla (hatchback 4,05 m, sedan 4,55 m, SUV 4,50 m, hafif ticari 4,40 m, taksi) çarpışma ve ADAS hedef hesabına girer. Senaryo olayları korunur: 3–7 s arasında orta şeritteki araç 6 m/s² ile trafik sıkışıklığı sonuna kadar durur, 10. saniyede sağ şeritteki yavaş ticari araç orta şeride kesme yapar.

### Tesla Taklacı Güvercin: uçuş

Taklacı Güvercin, Ekim 2026 tanıtımındaki rampanın önünde başlar: şeridin üstünde, yoldan çeyrek boru gibi kalkan, dik bir duvarla 9 m'ye çıkan ve tavana kıvrılan J biçimli bir pist (kırmızı kenar çizgileri, kesik orta çizgi, yanında çelik iskele). BAŞLAT'a dokununca araç yol kenarındaki uzak kameranın önünde rampaya tırmanır ve tavanda, fanların emişiyle ters durur (4,6 s). Bu sırada fizik başlamaz, trafik bekler ve kartta `STUDIO BEKLENİYOR` görünür; Esc veya DURAKLAT aracı başa döndürür, sonraki başlatma tırmanışı yeniler. Tavanda durunca sürüş başlar: araç bırakır, iticileriyle 1,5 tur fıçı dönüşü atıp yola iner, kamera da tam yere değerken normal görünümüne ulaşır. Tanıtımda açıklandığı gibi iticiler basınçlı havayla çalışır ve yolda yeniden dolar. Sürüşte:

| Tuş | Davranış |
|---|---|
| **R** | Bir uçuş katmanı yüksel: yol → 4 m → 9 m. Yerdeyken kalkış için hız gerekmez; tüpte iniş yedeği ve 60 kg pay yoksa reddedilir (**HAVA TÜPÜ AZ**). |
| **F** | Bir katman alçal; 4 m'den iniş. Önümüzdeki 2 s içinde alttaki şeritte araç olacaksa iniş reddedilir ve **İNİŞ ŞERİDİ DOLU** görünür. |
| **Z / X** | Yolda takla: araç 0,75 m sıçrayıp 2,2 s'de şerit değiştirirken tam tur döner (≈12–14 kg hava). Havada yan iticilerle 2,4 s'de şerit değiştirir ve döner. Tüpte yeterli hava yoksa reddedilir (**HAVA TÜPÜ AZ**). |
| **A / D** | Yolda direksiyon; havada yan iticilerle yana kayar. |
| **W / S** | Havada arka ve burun iticileri 0,4 g iter/frenler; yolda motor ve frenler çalışır. **Boşluk**, S ile aynı freni kullanır. |

Fizik: 600 L karbon tüp, 700 bar / 15 °C'de ≈350 kg hava taşır; soğuk havanın çıkış hızı ≈640 m/s'dir (Isp ≈65 s). Her itme, itki ÷ çıkış hızı kadar hava harcar: 2,4 t'luk araç havada asılı kalmak için ≈34 kg/s yakar, yani dolu tüple fiziksel olarak ≈10 s havada kalır. Oyun kısa test sürüşleri için ölçeklenmiştir: hava 5,25 kat daha uzun yeter (dolu tüple ≈50 s uçuş, ≈6,5 kg/s) ve yolda çok daha hızlı dolar. Katmanlar arası çıkış/iniş hız ve ivme sınırlı bir referansı izler (en çok 4 m/s tırmanış, 5 m/s alçalma); kaldırma itkisi araç ağırlığının en çok 2 katıdır. Tüp, bulunulan yükseklikten iniş için gereken yedeğe (oyun ölçeğinde 7 kg + 1,4 kg/m) yaklaşınca araç kendiliğinden iner (**HAVA AZALDI · OTOMATİK İNİŞ**); yedek itme ve yan manevraya harcanmaz. 4,5 m/s'den sert yere değme kaza sayılır. Yolda tüp araç üstü kompresörle 17,5 kg/s dolar (boştan doluya ≈20 s); gerçek bir kompresör dolu tüp için yarım saat kadar çalışırdı. Üstteki **HAVA** göstergesi tüpteki kütleyi gösterir.

Havadaki araç bir aracın tavanından yüksekse o araçla çarpışmaz ve onu ADAS hedefi saymaz; karta "önde hedef yok" ölçümü gider, uyarı ve AEB yalnız yolda çalışır. Kart protokolü değişmez. İticiler yakmaz, parlamaz: basınçlı havanın yoğunlaştırdığı nem beyaz bir buğu olarak görünür, aracın hızıyla geride kalır ve yere çarpınca yayılır; ağızlıklar soğuktan buğulanır. Kanat uçuşta ve sert frende kalkar. Üstteki **UÇUŞ** göstergesi katmanı gösterir.

Kart, çarpışmaya 2,2 s kala uyarır (FCW; üretim araçlarında tipik 2–2,7 s). AEB son anda devreye girer: aracın kendi frenine göre (sürüş başında kalibre edilir: Şahin 7 m/s², Model 3 9,5 m/s², Taklacı Güvercin 14 m/s²) yaklaşma hızını 0,25 s tepki ve 2,5 m payla sıfırlayabileceği mesafede. Öndeki araç frenliyorsa kart bunu art arda ölçümlerden ölçer ve iki aracın da duracağı mesafeyi kullanır; 1,4 s'den yakın takipte öndekinin her an 6 m/s² ile frenleyebileceğini hesaba katar. Örneğin 200 km/sa'ten 80 km/sa giden araca yaklaşırken fren ≈80 m'de başlar (önceki sürümde ≈170 m'de).

| Saatteki mod | Davranış |
|---|---|
| AKTİF | Uyarı ve AEB çalışır; AEB gaz tuşundan önceliklidir. ACC ayrıca açılabilir. |
| UYARI | Uyarılar gösterilir; otomatik gaz/fren uygulanmaz. |
| KAPALI | ADAS uyarısı ve otomatik müdahale kapalıdır. |

Başka sayfaya/pencereye geçmek veya yolun klavye odağını kaybetmesi sürüşü duraklatır ve basılı tuşları bırakır. Yeniden başlatmak için ADASLab penceresini etkinleştirip Studio'daki veya saatteki BAŞLAT'ı kullanın. Normal kullanımda ayrıca bir Godot/debug penceresi veya ayrı oyun uygulaması açılmaz. Eski **Trafik oyunu** ve **ADASLab** sayfaları kaldırılmıştır.

## Görüntü ve iletişim

Qt Quick 3D `View3D`, sahneyi doğrudan Studio penceresinde GPU ile çizer (macOS'ta Metal, Windows'ta Direct3D 11, Linux'ta OpenGL). `ExtendedSceneEnvironment` ACES ton eşleme, ekran uzayı ortam gölgesi (SSAO), HDR ışıma (fren lambaları), hafif vinyet ve kaskadlı yumuşak gölgeler kullanır. Gökyüzü ve çevre aydınlatması (HDR ışık probu) gerçek bir HDRI fotoğrafından, asfalt ve çim taranmış fotoğraf dokularından gelir; kaynaklar CC0 Poly Haven'dır ([ATTRIBUTION.md](device_studio/qml/assets/ATTRIBUTION.md)). İki yönlü otoyol; asfalt dokusu, tekerlek izleri, şerit/kenar çizgileri ve titreşim bandı özel shader'da, kaydırılan dünya koordinatlarında çizilir. Çevrede orta refüj bariyeri, W profilli korkuluklar, aydınlatma direkleri, tabela köprüsü, hız sınırı levhası, üst geçit, ağaçlık alanlar, tarlalar, uzak dağlar ve rüzgâr türbinleri vardır; karşı yönde yalnız görsel trafik akar. Tekrarlanan nesneler instancing ile çizilir.

Ego araç giriş ekranında seçilir. **Tofaş Şahin**, 1980'lerin kutu tipi Türk sedanı oranlarında Blender'da modellenmiştir: sahnede gerçek 4,32 m boyunda, 2,49 m dingil mesafesi; pahlı gövde, gerçek cam ve çamurluk boşlukları, kapı/kaput derzleri, gömme dikdörtgen farlar ve ızgara, siyah tamponlar, yatay stoplar, aynalar, jant kapakları, TR plakalar ve koltuk, torpido, direksiyonlu iç mekân. **Tesla Model 3**, gerçek aracın ölçülerinde (4,69 m boy, 1,85 m en, 1,44 m yükseklik, 2,875 m dingil mesafesi) analitik kesitlerle Blender'da modellenmiştir: alçak yuvarlak burun, ön camdan arka cama kesintisiz koyu cam tavan, gövde renkli A/C direkleri, parlak siyah B direği ve çerçeveler, ince farlar ve gündüz farı şeridi, L biçimli stoplar ve üst stop lambası, 18 inç aero jant kapakları, gömme kapı kolları, TR plakalar ve yüzen orta ekranlı sade iç mekân. İki model de logo içermez ve trafikte de görünür. **Tesla Taklacı Güvercin Serisi** (2028 Roadster), 15 Ekim 2026 tanıtımına göre köşeli kesitlerle modellenmiştir: burun ışık şeridinden ön tekerlek yuvasını geçip kuyruğa uzanan karakter çizgisiyle kama gövde, kaputun iki yanında yükselen ön çamurluklar, gizli köşe farları, altın tonlu camlı T‑top kabin ve beyaz orta omurga, ayna yerine kamera kanatçıkları, barge board ve siyah aero perdeler, tam genişlikte ince stop şeridi, açılır kuyruk kanadı, arka tamponun altında dört emme fanı ve Rocket donanımının basınçlı hava iticileri; 2,825 m dingil mesafesi ve 2,0 m genişlik yayımlanan değerlerdir, boy ve yükseklik tahmindir. Logo içermez; trafikte kullanılmaz. Trafik araçları da Blender'da gerçek ölçüleriyle modellenmiştir: Renault Clio sınıfı hatchback, Fiat Egea sınıfı sedan, Togg T10X / Hyundai Tucson sınıfı SUV (siyah çamurluk kaplamaları, tavan rayları), Fiat Doblo sınıfı hafif ticari (boyasız tamponlar, dikey stoplar, sac jantlar) ve tavanında ışıklı **TAKSİ** levhası, T plakalı sarı İstanbul taksisi; boyalı tavan, siyah çerçeveli camlar, karartılmış B direkleri, farlar ve gündüz farı şeritleri, ızgaralar, stop/geri vites/sinyal lambaları, aynalar, kapı derzleri ve kolları, alaşım jantlar, TR plakalar ve iç mekânla. Vernikli metalik boya, koyu cam, gündüz farları, fren ve sinyal lambaları, süspansiyon (frenlemede burun dalışı, şerit değiştirirken yatma) ve yön dönüşü vardır. Kamera hız ve ivmeyle hafifçe geri çekilir ve görüş açısını genişletir; sürekli titreşim yoktur, yalnız AEB'de kısa ve düşük frekanslı bir sarsıntı olur; sürüş öncesinde ve sonunda araç etrafında döner. Tüm model, doku ve ses çıktıları depodadır; Studio'yu çalıştırmak için Blender, Godot, numpy, Pillow veya OpenCV gerekmez (bkz. [3B varlıkları yeniden üretme](#3b-varlıkları-yeniden-üretme)).

Python işçisi USB/UART'ın tek sahibidir. Boştayken `J` sorgusu saatin ayarlarını ve BAŞLAT isteğini okur; Studio'daki BAŞLAT da önce `J` ile saatin güncel ayarlarını okur, sonra `H:1` saate sürüşün başladığını bildirir. Sürüşte 20 Hz CRC korumalı ölçümleri gönderir. Trafik/araç fiziği Python'da, FCW/AEB/ACC hesabı saatteki C kodunda çalışır. Yalnız doğrulanmış cevap fizik adımını 50 ms ilerletir. 3B çizim bu adımları simülasyon zamanıyla tamponlar ve ekran tazeleme hızında (120 Hz'e kadar) en yeni örneğin yaklaşık 100 ms gerisinden, iki örnek arasında hız bilgisiyle yumuşak eğri (Hermite) kullanarak çizer; seri hat gecikmesindeki dalgalanma hız sıçraması olarak görünmez. Saatin hassas hedef hızı sürüş başlarken bilgisayardan tekrar yazılmaz; 216 km/sa sınırı desteklenir.

Arka plan sorguları düğmeleri kilitlemez. Kontroller, telemetri ve port listeleri ayrı bildirimlerle güncellenir; 3B sahne ve klavye odağı her örnekte yeniden oluşturulmaz. Pencere kapanırken işçi duraklatma/temizlik işlemini bitirir. Aynı portu PuTTY, CubeIDE, ikinci Studio veya eski bağımsız oyunla açık tutmayın.

Firmware, Düello ve komut konsolu sayfaları korunmuştur. İşlem ayrıntıları alt çubuktaki **İşlem günlüğü** içindedir. Eski Godot bağımsız prototipinin geliştirici kaynakları [godot/README.md](godot/README.md) altında bulunur; Studio başlatıcısı bu prototipi çalıştırmaz.

## 3B varlıkları yeniden üretme

Yalnız modeli veya dokuları değiştirirken gerekir. Komutlar macOS, Windows ve Linux'ta aynıdır; Windows'ta `.venv/bin/python` yerine `.venv\Scripts\python.exe` yazın.

```sh
# Bir kez: resmi Blender'ı SHA256 doğrulamasıyla .tools/blender altına kurar, sistemi değiştirmez
.venv/bin/python tools/install_blender.py
# Şahin: tools/sahin_blender.py ile Blender'da modeller, Balsam ile Qt biçimine çevirir, Sahin.qml yazar
.venv/bin/python tools/build_sahin_model.py
# Model 3: tools/model3_blender.py ile modeller, Model3.qml yazar ve Vehicle3D ölçülerini yazdırır
.venv/bin/python tools/build_model3_model.py
# Taklacı Güvercin: tools/roadster_blender.py ile modeller; Roadster.qml itici ağızlıklarını ve kanadı da yazar
.venv/bin/python tools/build_roadster_model.py
# Trafik araçları: tools/traffic_blender.py beş gövde tipini modeller; Hatch/Sedan/Suv/Van/Taxi.qml yazar
.venv/bin/python tools/build_traffic_models.py
# Gökyüzü, ışık probu, yüzeyler ve sesler; numpy, Pillow ve opencv-python kurulu bir Python ister
python3 tools/generate_drive_assets.py --source <Poly Haven klasörü>
# Yalnız temas gölgesi ve itici buğusu dokuları (numpy, Pillow)
python3 tools/generate_drive_assets.py --only fx
```

`BLENDER_BIN` başka bir Blender'ı seçer; Windows'ta `C:\Program Files\Blender Foundation` altındaki, macOS'ta `/Applications` altındaki kurulum da kendiliğinden bulunur. Şahin, Model 3, Roadster ve trafik araçları Blender 5.2.3 ile doğrulanmıştır ve aynı girdiden her seferinde bayt bayt aynı dosyalar üretilir. `--source` klasöründe [ATTRIBUTION.md](device_studio/qml/assets/ATTRIBUTION.md)'deki Poly Haven dosyalarının 2k sürümleri ve gökyüzü için 8k HDR bulunmalıdır; bu kaynaklar depoya eklenmez.

## Firmware yükleme ve bootloader

**Firmware** sayfasındaki akış:

1. **Paket seç** ile `.dfw` dosyasını seçin. Kart, adres, kimlik, protokol, boyut, vektörler, SHA-256 ve CRC32 yüklemeden önce kontrol edilir. Geçersiz dosya seçilirse önceki seçim temizlenir.
2. **Yükle ve başlat** düğmesine basın ve gösterilen paket/yer değiştirme bilgisini onaylayın. Kartta tek uygulama saklanır; yenisi mevcut uygulamanın yerini alır.
3. İlerlemeyi izleyin. **İptal** yarım yüklemeyi kurtarma modunda bırakır; yükleme baştan tekrarlanır.
4. Flash CRC doğrulamasından ve uygulamanın hazır cevabından sonra başarı gösterilir; uygun çalışma sayfası açılır.

UART güncelleyici bootloader ve son 16 KiB saat günlüğüne yazmaz. Bootloader 921600 8N1, runtime 115200 8N1 kullanır; hız geçişini Studio yönetir. Dijital imza uygulanmaz.

**ST-LINK ile kontrol et**, Flash'taki DeviceBoot descriptor'ını okur. İletişim hatası “yüklü değil” sayılmaz. SWD okumasından sonra seri bağlantı kurulamazsa kartı RESET ile başlatıp yeniden bağlanın.

**DeviceBoot kur / güncelle**, seçilen `DeviceBoot.bin` dosyası için ayrıca onay ister. Önce tam 4 MiB yedek ve SHA-256 değeri `Backup/<timestamp>/` içine kaydedilir; sonra yalnız bootloader/commit sayfaları güncellenir. Saat günlüğü korunur. Eski adrese derlenmiş uygulama uyumlu paket yüklenene kadar çalışamaz. Yedek yolu işlem günlüğünde görünür.

**Bootloader’a geç** çalışan uygulamaya BOOT isteği gönderir. **Uygulamayı başlat** geçerli uygulamayı bootloader üzerinden çalıştırır. Kurtarma için USER butonunu basılı tutarak kartı resetleyin. Uygulama takılmışsa USER ile reset veya SWD teşhisi kullanılır.

ST-LINK işlemleri için STM32CubeProgrammer gerekir. Windows ve macOS CubeIDE içindeki varsayılan konumlar aranır. Farklı kurulumda `STM32_PROGRAMMER_CLI` ortam değişkenini yürütülebilir dosyanın tam yoluna ayarlayın.

`Firmware/` altında Smartwatch, Düello ve ADASLab paketleri vardır. Paket ZIP içinde `manifest.json` ve `firmware.bin` içerir. CLI araçları da korunur:

```sh
.venv/bin/python package_firmware.py ../Duello/Firmware/Duello.bin Firmware/Duello.dfw --name Duello
.venv/bin/python package_firmware.py ../smart_watch-main/Firmware/Smartwatch.bin Firmware/Smartwatch.dfw --name Smartwatch
.venv/bin/python package_firmware.py ../ADASLab/Firmware/ADASLab.bin Firmware/ADASLab.dfw --name ADASLab --id 3 --version 3
.venv/bin/python flash_cli.py Firmware/ADASLab.dfw --port /dev/cu.usbmodem11103
```

Port örneğini kendi portunuzla değiştirin; Windows'ta örneğin `COM5` olabilir. CLI ile çalışırken Studio bağlantısını kapatın.

## Düello ve genel komutlar

Düello sayfasında **Silahı çıkar**, **Ateş et**, **Silahı yerine koy**, **Yeniden doldur**, **Yürü**, **Dur** ve **Sahneyi sıfırla** kontrolleri vardır. Silah, eylem, mermi ve hedef durumu karttan okunur. Animasyon sırasında firmware meşgul cevabı verebilir. Beş saniye komut/heartbeat gelmezse yürüme durur. Çizimler cihazda yapılır; PC video/piksel akışı göndermez.

Komut konsolu bağlı uygulamanın desteklediği tek token, en fazla 39 ASCII karakterlik komutları gönderir. `HELLO` ve `STATUS` ortak runtime komutlarıdır. `BOOT` bootloader geçişini yönetir; sonrasında kimlik/durum yenilenir. Smartwatch, cihaz besleniyorsa Studio kapalıyken de bağımsız çalışır.

## Yeni firmware ekleme

DeviceBoot revizyon 2 / protokol 1 uygulama kimliklerini genişletebilir. Kullanılan kimlikler: `1=Smartwatch`, `2=Duello`, `3=ADASLab`. Yeni uygulamalar için benzersiz `4..0xFFFFFFFE` kimliği kullanın; `0` ve `0xFFFFFFFF` ayrılmıştır. Studio desteklenmeyen kimliği eski bootloader'a **BEGIN/Flash silme başlamadan** reddeder.

Yeni firmware, uygulama adresi `0x0800A000`, descriptor `+0x400`, ayrılmış son 16 KiB ve RAM mailbox düzenine uymalıdır:

```c
#include "device_contract.h"
__attribute__((section(".app_info"), used))
const device_app_info_t device_app_info = { DEVICE_APP_MAGIC, 4U, 1U, DEVICE_PROTOCOL };
```

`device_runtime_init("MyApp", handler)` ortak HELLO/STATUS/BOOT ve kimlik/sürüm cevabını sağlar. `handler(const char *command)` geçerli JSON nesnesine işaretçi döndürür. UART/DMA bağlantısı için Düello veya ADASLab kaynaklarını örnek alın. Tam cevap 512 bayt TX tamponuna sığmalıdır.

```sh
.venv/bin/python package_firmware.py ../MyApp/Firmware/MyApp.bin Firmware/MyApp.dfw --name MyApp --id 4 --version 1
```

Kimlik ve sürüm varsayılan olarak binary descriptor'ından okunur; uyuşmayan açık değerler reddedilir. Ad 1–48 karakter olmalı, ASCII harfle başlamalı ve yalnız harf/rakam, `_`, `.`, `-` içermelidir. Mevcut uygulama adları/kimlikleri tekrar kullanılmamalıdır. Runtime adı paket adıyla eşleşmelidir. Özel arayüzü olmayan uygulama Komut konsolu sayfasında kontrol edilebilir.

## Testler

```sh
.venv/bin/python -m unittest discover -s tests -v
# Genel sayfalar, yükleme onayı ve konsol; sanal cihaz, Flash yazılmaz:
.venv/bin/python tools/verify_qt_ui.py
# Yenileme sırasında gerçek fare/klavye, taslak metin ve odak:
.venv/bin/python tools/verify_qt_interaction.py
# Gerçek 3B pencere + derlenmiş ARM C kodu ve saat dokunma işleyicisi:
.venv/bin/python tools/verify_game_ui.py --capture-dir build/embedded-3d-arm
# Aynı akış, önceden yüklü fiziksel kartta (portu kendi cihazınızla değiştirin):
.venv/bin/python tools/verify_game_ui.py --backend hardware --port /dev/cu.usbmodem11403 --capture-dir build/embedded-3d-hardware
```

3B arayüz testleri Qt'nin yerel RHI/GPU çizimini gerektirir; `QT_QUICK_BACKEND=software` View3D çizmez. ARM testi LVGL'nin çağırdığı gerçek `adas_game_touch` fonksiyonunu çalıştırır. Fiziksel kart testindeki ayar/başlat istekleri mevcut G/H protokolünün eşdeğeridir; fiziksel parmak dokunuşu otomatikleştirilmez. Bu kontroller Flash'a yazmaz. Donanım testi öncesi açık Studio bağlantısını kapatın.

Windows'ta komutlarda `.venv\Scripts\python.exe` ve `COM5` gibi bir port adı kullanın.

Güncel sonuçlar [embedded-3d-verification.json](embedded-3d-verification.json), ekran görüntüleri `build/embedded-3d-*/` altındadır. Önceki `game-verification.json`, `godot-verification.json`, `standalone-verification.json` önceki mimarilerin kayıtlarıdır. Windows başlatıcısı aynı giriş noktasını kullanır. 3B sahne macOS'ta Metal ile uçtan uca doğrulanmıştır; Windows'un Direct3D 11 ve Linux'un OpenGL arka ucu için sahnenin ürettiği tüm shader'ların HLSL 5.0, GLSL 330 ve GLSL ES 3.0'a çevrildiği `qsb` ile denetlenmiştir. Gerçek bir Windows makinesinde henüz çalıştırılmamıştır.

Normal uygulama dönüşü başka `.dfw` paketini yüklemektir. İlk bootloader kurulumu öncesine tam dönüş, `Backup/<timestamp>/before-deviceboot-flash.bin` dosyasını SWD ile `0x08000000` adresine doğrulayarak geri yüklemektir. Bu tüm Flash'ı ve yedekteki saat kayıtlarını geri getirir. Yedekler, `.venv`, yerel bağımlılıklar ve kişisel ayarlar Git'e dahil edilmez.

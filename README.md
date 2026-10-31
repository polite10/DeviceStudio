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

ADASLab sürüş sayfasıyla açılır ve seçili ST-LINK seri portuna otomatik bağlanır. Sol menüde ayrı bir sürüş öğesi yoktur; üstteki **ADASLab** logosu diğer sayfalardan sürüşe döner. USB sonradan takıldıysa üstteki yenile düğmesiyle portları taratıp **Bağlan** seçin. `--game` de aynı Studio görünümünü açar. `--game-sim` fiziksel karta erişmeden derlenmiş ARM firmware'ini kullanır. Eski `--adas` / `--game-2d` seçenekleri bu yeni görünüme uyumluluk takma adıdır; eski ekranları açmaz.

## Saatten başlat, Studio'da oyna

Kartta **ADASLab v2 (ID 3)** ve DeviceBoot v2 bulunmalıdır. Masaüstündeki grafik değişiklikleri için firmware yeniden yüklenmez; kart ekranının yeni arayüzü için güncel `Firmware/ADASLab.dfw` paketini yükleyin.

1. Saati ST-LINK USB bağlantısıyla bağlayın, ADASLab'ı açın ve sürüş görünümünü etkin bırakın.
2. Giriş ekranındaki kartın **Aracını seç** bölümünden **Tofaş Şahin** veya **Tesla Model 3**'ü seçin. Seçilen araç vitrinde döner, sürüşte kullanılır ve sonraki açılışta hatırlanır.
3. Saatten **AKTİF / UYARI / KAPALI**, **ACC**, hedef hız **− / +** ve **TAKİP** ayarını seçin. Studio'nun üst göstergeleri bu değerleri salt okunur gösterir.
4. Saatte **BAŞLAT** düğmesine dokunun. Oyun Studio'nun içindeki 3B sahnede başlar ve klavye odağı otomatik yola geçer.
5. **W / ↑** gaz, **S / ↓** fren, **A–D / ← →** şerit değişimidir. Şerit tuşuna her basış bir şerit ister; otomatik tuş tekrarı ek şerit değişimi oluşturmaz. **C** takip/kaput kamerasını, **V** ADAS çizimlerini, **M** sesi açıp kapatır.
6. Saatte **DURAKLAT**, bilgisayarda **Boşluk / Esc** sürüşü duraklatır. Saatte tekrar **BAŞLAT** aynı yolu sürdürür. Çarpışma veya 120 simülasyon saniyesi sonunda sonraki BAŞLAT yeni sürüş hazırlar.

Sol alttaki gösterge paneli hızı, ACC hedef hız işaretini, ACC/FCW/AEB uyarı lambalarını, sinyal oklarını, takip süresini ve gaz/fren ivmesini gösterir. Sağ alttaki **Sensör görünümü** 110 m içindeki araçları şeritleriyle çizer; öndeki araç vurgulanır, takip mesafesi, TTC ve bağıl hız altında yazar. 3B sahnede öndeki araç ADAS kamera çerçevesiyle işaretlenir; ego şeridindeki **takip koridoru** hıza göre gereken takip mesafesini gösterir ve öndeki araç bu mesafeye girince sarıya, AEB'de kırmızıya döner. Sarı **ÇARPIŞMA UYARISI** FCW'yi, kırmızı **AEB · ACİL FREN** gerçek firmware'in acil fren isteğini ekran kenarı uyarısı ve sesli uyarıyla gösterir. Sürüş bitince puan, mesafe, uyarı, AEB müdahalesi, ramak kala ve ortalama tepki süresi özetlenir. ACC açıkken pedallara basmazsanız hedef hız ve takip süresini saat yönetir. Mod ve durum kart ekranında da izlenebilir.

| Saatteki mod | Davranış |
|---|---|
| AKTİF | Uyarı ve AEB çalışır; AEB gaz tuşundan önceliklidir. ACC ayrıca açılabilir. |
| UYARI | Uyarılar gösterilir; otomatik gaz/fren uygulanmaz. |
| KAPALI | ADAS uyarısı ve otomatik müdahale kapalıdır. |

Başka sayfaya/pencereye geçmek veya yolun klavye odağını kaybetmesi sürüşü duraklatır ve basılı tuşları bırakır. Yeniden başlatmak için ADASLab penceresini etkinleştirip saatte BAŞLAT kullanın. Normal kullanımda ayrıca bir Godot/debug penceresi veya ayrı oyun uygulaması açılmaz. Eski **Trafik oyunu** ve **ADASLab** sayfaları kaldırılmıştır.

## Görüntü ve iletişim

Qt Quick 3D `View3D`, sahneyi doğrudan Studio penceresinde GPU ile çizer (macOS'ta Metal, Windows'ta Direct3D 11, Linux'ta OpenGL). `ExtendedSceneEnvironment` ACES ton eşleme, ekran uzayı ortam gölgesi (SSAO), HDR ışıma (fren lambaları), hafif vinyet ve kaskadlı yumuşak gölgeler kullanır. Gökyüzü ve çevre aydınlatması (HDR ışık probu) gerçek bir HDRI fotoğrafından, asfalt ve çim taranmış fotoğraf dokularından gelir; kaynaklar CC0 Poly Haven'dır ([ATTRIBUTION.md](device_studio/qml/assets/ATTRIBUTION.md)). İki yönlü otoyol; asfalt dokusu, tekerlek izleri, şerit/kenar çizgileri ve titreşim bandı özel shader'da, kaydırılan dünya koordinatlarında çizilir. Çevrede orta refüj bariyeri, W profilli korkuluklar, aydınlatma direkleri, tabela köprüsü, hız sınırı levhası, üst geçit, ağaçlık alanlar, tarlalar, uzak dağlar ve rüzgâr türbinleri vardır; karşı yönde yalnız görsel trafik akar. Tekrarlanan nesneler instancing ile çizilir.

Ego araç giriş ekranında seçilir. **Tofaş Şahin**, 1980'lerin kutu tipi Türk sedanı oranlarında Blender'da modellenmiştir: 4,5 m boy, 2,49 m dingil mesafesi; pahlı gövde, gerçek cam ve çamurluk boşlukları, kapı/kaput derzleri, gömme dikdörtgen farlar ve ızgara, siyah tamponlar, yatay stoplar, aynalar, jant kapakları, TR plakalar ve koltuk, torpido, direksiyonlu iç mekân. **Tesla Model 3**, gerçek aracın ölçülerinde (4,69 m boy, 1,85 m en, 1,44 m yükseklik, 2,875 m dingil mesafesi) analitik kesitlerle Blender'da modellenmiştir: alçak yuvarlak burun, ön camdan arka cama kesintisiz koyu cam tavan, gövde renkli A/C direkleri, parlak siyah B direği ve çerçeveler, ince farlar ve gündüz farı şeridi, L biçimli stoplar ve üst stop lambası, 18 inç aero jant kapakları, gömme kapı kolları, TR plakalar ve yüzen orta ekranlı sade iç mekân. İki model de logo içermez ve trafikte de görünür. Diğer trafik araçları CC0 Quaternius modellerinin Qt biçimine dönüştürülmüş beş sürümüdür. Vernikli metalik boya, koyu cam, gündüz farları, fren ve sinyal lambaları, süspansiyon (frenlemede burun dalışı, şerit değiştirirken yatma) ve yön dönüşü vardır. Kamera hız ve ivmeyle hafifçe geri çekilir ve görüş açısını genişletir; sürekli titreşim yoktur, yalnız AEB'de kısa ve düşük frekanslı bir sarsıntı olur; sürüş öncesinde ve sonunda araç etrafında döner. Tüm model, doku ve ses çıktıları depodadır; Studio'yu çalıştırmak için Blender, Godot, numpy, Pillow veya OpenCV gerekmez (bkz. [3B varlıkları yeniden üretme](#3b-varlıkları-yeniden-üretme)).

Python işçisi USB/UART'ın tek sahibidir. Boştayken `J` sorgusu saatin ayarlarını ve BAŞLAT isteğini okur; sürüşte 20 Hz CRC korumalı ölçümleri gönderir. Trafik/araç fiziği Python'da, FCW/AEB/ACC hesabı saatteki C kodunda çalışır. Yalnız doğrulanmış cevap fizik adımını 50 ms ilerletir. 3B çizim bu adımları simülasyon zamanıyla tamponlar ve ekran tazeleme hızında (120 Hz'e kadar) en yeni örneğin yaklaşık 100 ms gerisinden, iki örnek arasında hız bilgisiyle yumuşak eğri (Hermite) kullanarak çizer; seri hat gecikmesindeki dalgalanma hız sıçraması olarak görünmez. Saatin hassas hedef hızı sürüş başlarken bilgisayardan tekrar yazılmaz; 216 km/sa sınırı desteklenir.

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
# Trafik araçları: Quaternius FBX dosyalarını Qt biçimine çevirir
.venv/bin/python tools/import_qt_vehicles.py
# Gökyüzü, ışık probu, yüzeyler ve sesler; numpy, Pillow ve opencv-python kurulu bir Python ister
python3 tools/generate_drive_assets.py --source <Poly Haven klasörü>
```

`BLENDER_BIN` başka bir Blender'ı seçer; Windows'ta `C:\Program Files\Blender Foundation` altındaki, macOS'ta `/Applications` altındaki kurulum da kendiliğinden bulunur. Şahin ve Model 3, Blender 5.2.3 ile doğrulanmıştır ve aynı girdiden her seferinde bayt bayt aynı dosyalar üretilir. `--source` klasöründe [ATTRIBUTION.md](device_studio/qml/assets/ATTRIBUTION.md)'deki Poly Haven dosyalarının 2k sürümleri ve gökyüzü için 8k HDR bulunmalıdır; bu kaynaklar depoya eklenmez.

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
.venv/bin/python package_firmware.py ../ADASLab/Firmware/ADASLab.bin Firmware/ADASLab.dfw --name ADASLab --id 3 --version 2
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

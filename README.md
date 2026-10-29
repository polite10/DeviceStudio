# Device Studio

Python + PySide6 / Qt Quick masaüstü uygulaması. [DeviceBoot](https://github.com/polite10/DeviceBoot) yönetimi, firmware yükleme, [Düello](https://github.com/polite10/Duello) kontrolü, ADASLab sürüş deneyleri ve klavyeyle oynanan trafik oyununu tek arayüzde toplar. Kartın C firmware'i ve UART protokolü arayüzden bağımsızdır.

## Kurulum ve açılış

Python 3.12+ gerekir. Bağımlılıklar `requirements.txt` içinde sabitlenmiştir: `PySide6==6.12.0`, `pyserial==3.5`. Başlatıcılar proje içindeki `.venv` ortamını oluşturur; gereksinim dosyası değiştiğinde veya temel bağımlılıklar eksikse kurulum yapar. Sonraki açılışlar aynı ortamı kullanır.

Windows / PowerShell:

```powershell
./Start.ps1
# Karttaki ADASLab'a bağlanıp varsayılan deneyi başlat:
./Start.ps1 --adas
# İsteğe bağlı eski QML deney görünümü:
./Start.ps1 --game-2d
```

macOS:

```sh
./Start.command
./Start.command --adas
./Start.command --game
```

Elle kurulum ve çalıştırma:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python studio.py
```

Windows'ta son iki komut için `.venv\Scripts\python.exe` kullanın. Başlatma seçenekleri:

| Seçenek | Davranış |
|---|---|
| Seçenek yok | Arayüzü Trafik oyunu sayfasında açar; bağlantıyı kullanıcı kurar. |
| `--connect` | Seçili ST-LINK seri portuna bağlanır. |
| `--adas` | Gerçek karta bağlanır; kartta ADASLab çalışıyorsa deneyi başlatır. Firmware yüklemez. |
| `--adas-sim` | Derlenen ARM ELF ile laboratuvar deneyini başlatır; fiziksel karta erişmez. |
| `--game` | Studio açmadan bağımsız release uygulamasını başlatır; ayarlar ve başlatma saatten yönetilir. |
| `--game-sim` | ARM ELF denetleyicisiyle Godot 3B oyununu açar; fiziksel karta erişmez. |
| `--game-2d` / `--game-2d-sim` | Mevcut QML trafik görünümünü gerçek kartla / ARM simülasyonuyla açar. |

ARM simülasyonu için ek bağımlılıkları aynı ortama kurun:

```sh
.venv/bin/python -m pip install -r requirements-sim.txt
.venv/bin/python studio.py --game-sim
```

Kardeş `ADASLab/build/ADASLab.elf` bulunmalıdır. SDK'nın yerel `tmp/simulator-libs` klasörü varsa kullanılabilir. Arayüz simülasyon modunu açıkça etiketler; GPU/ekran donanımı emüle edilmez, ilgili sayaçlar sıfırdır. Bu modda fiziksel firmware/bootloader yüklemesi kapalıdır.

## Bağlantı ve sayfalar

Kartı **ST-LINK USB** girişinden bilgisayara bağlayın. Aynı kablo SWD programlama/teşhis ve sanal seri port üzerinden USART1 haberleşmesini sağlar. Ek UART dönüştürücü gerekmez. Port numarası sabit değildir; üst çubuk ST-LINK portunu öncelikli seçer. Gerekirse **Yenile**, ardından **Bağlan** kullanın.

Solda beş sayfa vardır:

- **Trafik oyunu:** WASD/oklarla sürüş, üç ADAS modu ve sürüş sonuçları.
- **ADASLab:** Senaryo ayarları, yol görünümü, hız/mesafe/TTC, kontrol durumları ve ölçüm grafiği.
- **Firmware:** `.dfw` paket seçimi, yükleme ilerlemesi/iptali, bootloader ve kurtarma araçları.
- **Düello:** Karakterin yedi kontrol komutu ve cihazdan gelen durum.
- **Komut konsolu:** Genel uygulama komutları ve JSON durum görüntüsü.

Bağlantıdan sonra çalışan uygulamaya uygun sayfa açılır. Alt çubuktaki **İşlem günlüğü** ayrıntıları gösterir. Bootloader bilgisi ile çalışan uygulamanın kimliği ayrı gösterilir. Flash descriptor'ı kimliği belirtir; tek başına bütün bootloader kodunun sağlık kontrolü değildir.

PuTTY, başka bir Studio veya CubeIDE seri terminali aynı portu açık tutmamalıdır. Tek işçi seri portun sahibidir; deney, oyun veya yükleme sırasında çakışan komutlar kapalıdır. Boştaki durum sorgusu düğmeleri kilitlemez; sorgu sırasında yapılan kullanıcı işlemleri aynı seri işçide sıraya alınır. Telemetri, port listesi ve ayarlar ayrı bildirimlerle güncellendiği için seçimler ve klavye odağı her örnekte yeniden kurulmaz. Aktif işlem varken pencere kapatılırsa iptal/duraklatma istenir ve işçinin temizliği tamamlanınca kapanır. Kesilemeyen bootloader kurulumu tamamlanana kadar beklenir.

## ADASLab Drive — bağımsız oyun

3B oyun artık **Studio'dan bağımsız macOS release uygulamasıdır**. Kullanıcı Uygulamaları klasöründeki **ADASLab Drive.app** doğrudan açılır. Studio, Python, Godot editörü veya TCP köprüsü gerekmez; DEBUG başlığı yoktur.

Saat USB ile bağlanır. ADAS modu, ACC, hedef hız, takip süresi ve **BASLAT / DURAKLAT** saat ekranından yönetilir. Bilgisayarda WASD/oklar sürüş, Boşluk/Esc duraklatma ve C/F kamera değişimidir. Menü saatteki ADAS ayarlarını salt okunur gösterir.

Godot uygulaması yerel C++ seri port eklentisini kullanır. Trafik fiziği Godot'ta, ADAS kararları saatteki mevcut C firmware'inde çalışır. Mevcut ADASLab v2 yeterlidir; grafik/uygulama ayrımı için firmware yeniden yüklenmez.

```sh
# Geliştirici ortamında release paketi üretip kullanıcı Uygulamaları'na kurar:
.venv/bin/python tools/build_standalone.py --install
# Hazır bağımsız paketi açar; Studio/Python ortamını başlatmaz:
./Start.command --game
```

Ayrıntılar [bağımsız oyun belgesinde](godot/README.md). Studio firmware yükleme ve teşhis aracı olarak ayrıca kullanılabilir.

## Eski QML trafik görünümü (geliştirici)

Kartta **ADASLab v2 (ID 3)** ve DeviceBoot revizyon 2 bulunmalıdır. Eski ADASLab v1 laboratuvar deneyleri çalışmaya devam eder; oyun için v2 paketi yüklenir. Sensör gerekmez: trafik ve araç fiziği bilgisayarda, FCW/AEB/ACC kararları C firmware'inde çalışır. USB üzerinden ölçüm ve kontrol verisi taşınır; karttan video aktarılmaz.

1. `./Start.command --game` (Windows: `./Start.ps1 --game`) ile açın veya Studio'da **Bağlan**, ardından **Trafik oyunu** seçin. Kartın adı/sürümü ve hazır durumu görünmelidir.
2. Duraklatılmışken **Aktif destek**, **Yalnız uyarı** veya **ADAS kapalı** modunu seçin. İlk sürüşte **Aktif destek**, ACC kapalı ve varsayılan trafik tohumu `42` uygundur.
3. **Başlat** düğmesine basın. Yol alanı klavye odağını alır; **W / ↑** gaz, **S / ↓** fren, **A–D / ← →** şerit değişimidir. Sol/sağ tuşuna her basış bir şerit ister; basılı tutmak tekrar tekrar şerit değiştirmez.
4. **Boşluk** veya **Duraklat** sürüşü durdurur. **Devam et** aynı yolu sürdürür; **Yeniden dene** seçili tohumla yolu sıfırlar. Başka sayfaya/pencereye geçmek veya yolun klavye odağını kaybetmesi de oyunu duraklatır ve basılı tuşları bırakır.
5. Hız, mesafe, TTC, uyarı ve fren durumunu izleyin. Oyun çarpışmada veya 120 simülasyon saniyesinde biter; sonuçta puan, mesafe, çarpışma ve müdahale sayıları görünür. Son dokuz sonuç oturumda saklanır; panel en yeni üçünü gösterir.

| Mod | Sürücünün ve sistemin görevi |
|---|---|
| **Aktif destek** | Sistem uyarır ve tehlikede AEB fren isteği uygular; acil fren gaz tuşundan önceliklidir. ACC ayrıca açılabilir. |
| **Yalnız uyarı** | Uyarı/TTC görünür; otomatik gaz veya fren uygulanmaz. Fren sürücüye aittir. |
| **ADAS kapalı** | ADAS uyarıları ve otomatik müdahale kapalıdır; araç tamamen sürücünün gaz/fren komutlarını izler. |

**ACC** yalnız aktif destek modunda kullanılabilir. Pedallara basılmadığında hedef hız ve takip süresine göre hız ayarlar; gaz veya fren basıldığında o adımda sürücü komutu geçerlidir, AEB önceliği korunur. Farklı modları karşılaştırmak için aynı trafik tohumunu seçip **Yeniden dene** kullanın; aynı sürücü girdileriyle karşılaştırma daha anlamlıdır. Trafikte ani fren ve şerit kesme olayları vardır. Bu model bir eğitim oyunudur; her koşulda çarpışmayı önleme garantisi vermez.

**Kart ekranı yardımcı kontrol panelidir.** Studio oyun sayfasındayken kartta `ADASLAB / DRIVE` görünür. Duraklatılmışken **AKTIF / UYARI / KAPALI**, **ACC**, hedef hız **− / +** ve **TAKIP** seçilebilir. **BASLAT / DURAKLAT** isteği USB üzerinden Studio'ya iletilir; sürüş sırasında ayar değişiklikleri kilitlenir, duraklatma kullanılabilir. Karttan başlatma için Studio bağlı, oyun sayfası açık ve pencere etkin olmalıdır. Karttaki hız, `MESAFE`, `TTC`, `IVME/FREN` ve `AEB/WARNING` durumları PC'deki sürüşle birlikte değişir. Direksiyon, gaz ve fren bilgisayar klavyesindedir.

Her onaylanmış ölçüm fiziği 50 ms ilerletir. Cevap kesilirse oyun ilerlemez; 500 ms eski veride firmware ivme isteğini sıfırlar. Oyun denetleyicisi ayrı komutlar kullanır; aşağıdaki hazır laboratuvar senaryoları korunmuştur.

## ADASLab: ilk deney

Kartta DeviceBoot revizyon 2 ve ADASLab (ID 3) yüklü olmalıdır. Fizik Studio'da, FCW/AEB/ACC kararları kartta çalışır. Kartın fren isteği sanal aracı yavaşlatır.

1. **Bağlan** ve **ADASLab** sayfasını açın.
2. İlk ACC deneyi için **Yavaş araç**, hedef **90 km/sa**, **ACC** ve **AEB** açık seçin. Başlangıçta **Gürültü** ve **Tekrar** kapalı olabilir.
3. **Deneyi başlat** düğmesine basın. Hızın öndeki araca uyumunu, takip mesafesini ve ivme isteğini izleyin.
4. **Deneyi duraklat** ile durdurun; işlem tamamlanınca ayarları değiştirebilirsiniz.
5. AEB için **Ani fren** senaryosunu seçip başlatın. Öndeki araç üçüncü saniyede fren yapar. `WARNING` uyarısını ve gerekirse `AEB` durumuna geçişi izleyin.
6. Deneyden sonra **CSV kaydet** ile ölçümleri dışa aktarın. En son 12.000 örnek saklanır.

| Senaryo | Deney |
|---|---|
| Ani fren | Öndeki aracın frenine takip ve acil fren tepkisi. |
| Yavaş araç | Daha yavaş araca yaklaşırken ACC'nin hız/mesafe ayarı. |
| Önümüze giren araç | Üçüncü saniyede yeni hedefin ortaya çıkması. |
| Sabit takip | Aynı hızdaki iki araçla bağlantı ve sabit takip kontrolü. |
| Veri kesintisi | Ölçüm akışı kısa süre kesildiğinde veri eskime koruması. |

**ACC**, hedef hızı ve takip mesafesini korumaya çalışır. **AEB**, acil durumda daha güçlü fren isteği üretir. ACC de normal yavaşlama yapabildiğinden AEB'yi değerlendirirken sistemin `AEB` durumunu ve fren isteğini birlikte izleyin. **Gürültü** ölçümlere sapma ekler; **Tekrar** açıkken deney 25 simülasyon saniyesi sonunda yeniden başlar.

Kart ekranında hız, öndeki araç, `MESAFE`, `TTC`, ivme/fren ve sistem modu görünür. `TTC --` yaklaşma olmadığını belirtir. `WAITING` ölçüm bekleme, `ACC` takip kontrolü, `WARNING` çarpışma uyarısı, `AEB` acil fren, `PAUSED` duraklatma, `NO_DATA` veri eskimesidir. `GPU` ve `KARE` tamamlanmış iş/sunum sayaçlarıdır; doğrudan FPS değildir.

Ölçüm hedefi 50 ms'dir. Fizik zamanı her onaylı cevapta 50 ms ilerler; geç cevaplar deneyi yavaşlatır, komut biriktirilmez. Seri cevap gelmezse fizik ilerletilmez. Kart 500 ms yeni ölçüm almazsa `NO_DATA` durumuna geçip ivme isteğini sıfırlar. Duraklatma sonunda `PAUSE` gönderilir. QML görünümü sınırlı kuyruğun en güncel örneğini tüketir; seri işçi arayüzden bağımsızdır.

Ölçümler CRC16-CCITT (`0x1021`, başlangıç `0xFFFF`, ondalık son alan), sıra numarası ve simülasyon zamanıyla doğrulanır. RTT, 50 ms aşımı, kontrol süresi, GPU tamamlanması, kare sayısı ve en uzun kare izlenebilir. Protokol/IRQ/GPU tasarımı [ADASLab README](../ADASLab/README.md) içindedir. Bunlar sanal araç deneyleridir; deney kalibrasyonları gerçek araç kullanımı için doğrulanmamıştır.

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

## Testler, raporlar ve geri dönüş

Yerel testler fiziksel karta bağlanmaz:

```sh
.venv/bin/python -m unittest discover -s tests -v
# QML ekranları, düğme bağlantıları ve 1000×720 yerleşim kontrolü:
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software .venv/bin/python tools/verify_qt_ui.py
# Yenileme sırasında düğme, seçim ve klavye odağı regresyonları:
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software .venv/bin/python tools/verify_qt_interaction.py
# Oyun fiziği + gerçek derlenmiş ARM kontrolü; fiziksel karta erişmez:
.venv/bin/python tools/verify_game_arm.py
# Gerçek QML oyun kontrolleri + ARM firmware; fiziksel karta erişmez:
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software .venv/bin/python tools/verify_game_ui.py
# Derlenen ARM ELF ile laboratuvar arayüz testi (fiziksel karta erişmez):
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software .venv/bin/python tools/verify_qt_ui.py --backend arm
```

İlk Qt geçişinde 45 birim/denetleyici testi, uyarısız QML lint kontrolü, ARM simülasyonu ve mevcut ADASLab kartıyla arayüz akışı doğrulandı. macOS'ta masaüstü çizim motoru Metal olarak çalıştı. Özet `qt-verification.json`, yerel ekran görüntüleri ve ayrıntılar `build/qt-preview-*/` içindedir. Yeni arayüz testi firmware veya bootloader yüklemedi. Windows başlatıcısı güncellendi; bu bilgisayarda Windows üzerinde çalıştırılmadı.

Oyun testleri üç modun ayrılmasını, aynı tohumla trafik tekrarını, gaz/fren önceliğini, odak kaybında duraklamayı, bağımsız tuş basışlarını ve kart paneli protokolünü sınar. `tools/verify_game_arm.py` çıktısı `build/game-arm-policy-report.json`, `tools/verify_game_ui.py` çıktısı `build/game-ui-qa/` altındadır. ARM testleri gerçek derlenmiş C kodunu çalıştırır; fiziksel dokunmatik paneli veya GPU donanımını emüle etmez.

Bu oyun sürümünde 72 birim testi, 16 yenileme etkileşimi, 22 ARM trafik kontrolü ve 58 QML oyun kontrolü geçti. QML oyun akışı ARM ile hem yazılım çiziminde hem macOS Metal üzerinde, gerçek kartla yazılım çiziminde doğrulandı. Gerçek karttaki 14 kontrol ACC/AEB, üç mod, paket/zaman doğrulaması ve GPU/LCD sayaçlarını kapsadı; eski laboratuvar/firmware/konsol arayüzündeki 41 kontrol de v2 kartla geçti. Özet [game-verification.json](game-verification.json) içindedir.

4 MiB yükleme öncesi yedek `Backup/before-game-v2-20261028-223216/flash.bin` konumundadır. SWD okuması, yüklenen v2 uygulamanın test edilen binary ile birebir eşleştiğini ve bootloader kodu ile son 16 KiB saat günlüğünün değişmediğini doğruladı. Fiziksel parmak dokunuşu otomatikleştirilmedi; LVGL düğmelerinin çağırdığı işlevler derlenen ARM testinde sınandı.

Önceden yüklenmiş v2 kartta oyun testlerini çalıştırmak için (önce Studio bağlantısını kapatın):

```sh
.venv/bin/python tools/verify_game_hardware.py --port /dev/cu.usbmodem11103
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software .venv/bin/python tools/verify_game_ui.py --backend hardware --port /dev/cu.usbmodem11103 --capture-dir build/game-ui-hardware
```

Bu iki test Flash'a yazmaz. `--game` / `--game-sim` sürüşü kendiliğinden başlatmaz; pencereyi etkinleştirip **Sürüşü başlat** kullanın.

Mevcut ADASLab yüklenmiş fiziksel kartla laboratuvar QML testi için (portu kendi cihazınızla değiştirin, önce açık Studio'yu kapatın):

```sh
.venv/bin/python tools/verify_qt_ui.py --backend hardware --port /dev/cu.usbmodem11103
```

Bu test ölçüm ve `PAUSE` komutları gönderir, firmware yükleme onayını açıp **vazgeçer**. Ekran görüntüleri, bağlanma/başlatma/duraklatma ve CSV/komut akışları birlikte kontrol edilir. Windows'ta `QT_QPA_PLATFORM` ortam değişkenini PowerShell sözdizimiyle ayarlayın veya normal pencereyle çalıştırın.

Donanım testleri ayrıca ve açıkça çalıştırılır. Aynı seri port başka programda açık olmamalıdır:

```sh
# Önceden yüklenmiş ADASLab üzerinde ölçüm/koruma testleri; firmware yüklemez:
.venv/bin/python verify_adas_hardware.py --port /dev/cu.usbmodem11103
# Gerçek firmware'i değiştirir, sonunda Smartwatch'ı geri yükler:
.venv/bin/python verify_hardware.py --port COM5
# İlk bootloader kurulumu da yapılacaksa:
.venv/bin/python verify_hardware.py --port COM5 --install
```

`verify_hardware.py` için kart önce bootloader modunda olmalıdır. `hardware-report.json` önceki iki-uygulama UART yükleme/kurtarma testlerine; `adas-hardware-report.json` önceki ADASLab kart testine aittir. ADASLab raporundaki 960 örnek, yaklaşık 32 ms ortalama/43.47 ms en yüksek RTT, 20 µs kontrol ve 35 ms en uzun kare sonuçları o donanım testinin ölçümleridir. Bu kayıtlar yeni Qt arayüzünün ayrıca sınandığı veya uzun süreli/güç kesintili doğrulama yapıldığı anlamına gelmez.

Normal uygulama dönüşü başka `.dfw` paketini yüklemektir. İlk bootloader kurulumu öncesine tam dönüş, `Backup/<timestamp>/before-deviceboot-flash.bin` dosyasını SWD ile `0x08000000` adresine doğrulayarak geri yüklemektir. Bu tüm Flash'ı, bootloader'ı ve yedekteki saat kayıtlarını geri getirir. Daha güncel saat kayıtlarını korumak için son 16 KiB'ı ayrıca yedekleyin. Otomatik eski sürüm rollback'i yoktur. Yedekler, `.venv`, yerel bağımlılıklar ve kişisel ayarlar Git'e dahil edilmez.

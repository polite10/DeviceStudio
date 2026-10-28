# Device Studio

Python/Tk masaüstü uygulaması (mevcut ST-LINK araç keşfi Windows içindir): [DeviceBoot](https://github.com/polite10/DeviceBoot) yönetimi, firmware yükleme ve [Düello](https://github.com/polite10/Duello) kontrolü. [Smartwatch](https://github.com/polite10/smart_watch) yüklenince cihaz bağımsız çalışır; Düello yüklenince karakter kontrol paneli açılır.

## Çalıştırma

Python 3.12+ ve Tk gerekir. Seri bağlantı bağımlılığı `pyserial==3.5`.

```powershell
./Start.ps1
# Alternatif:
python -m pip install -r requirements.txt
python studio.py
```

`Start.ps1`, varsa bilgisayardaki Codex paketli Python'u kullanır ve pyserial'ı proje içindeki, Git'e dahil edilmeyen `.deps/` klasörüne kurar. Aksi halde PATH'teki Python'u kullanır. Tk içermeyen Python dağıtımlarında Tk içeren standart Windows Python kurun.

## Tek kabloyla kullanım

Kartın ST-LINK Micro USB girişini bilgisayara bağlayın. Programlama/teşhis SWD; uygulama kontrolü ST-LINK sanal COM portu üzerinden USART1 kullanır. Ek UART dönüştürücü gerekmez. COM numarası sabit değildir; arayüz portları listeler.

1. İlk açılış **Firmware yükleme** sekmesidir. Portu seçip **Bağlan** düğmesine basın.
2. **ST-LINK ile kontrol et**, Flash'taki DeviceBoot kimliğini okur. Cevap alınamaması “yüklü değil” kabul edilmez; hata ayrıca gösterilir.
3. İlk kurulum gerekiyorsa **DeviceBoot kur** ile `DeviceBoot/Firmware/DeviceBoot.bin` seçin. Önce tam 4 MiB yedek alınır. Yedeğin yolu logda görünür. Bootloader kurulduktan sonra uyumlu uygulama paketi yüklenmelidir.
4. **Firmware seç** ile uyumlu bir `.dfw` paketi seçin; **Yükle ve başlat** ile yükleyin. Cihazdaki mevcut uygulamanın yerini alır; saat kayıt günlüğü korunur.
5. Önce “Firmware doğrulandı”, uygulamanın JSON cevabı geldikten sonra “Uygulama hazır” gösterilir. Düello kontrol sekmesi otomatik açılır.

Bootloader durumu ile çalışan uygulama ayrı gösterilir. Smartwatch veya Düello, bootloader'ın Flash kimliğini bildirir. Bootloader modunda DeviceBoot sürüm/protokol/bellek sınırlarını doğrudan döndürür. Flash descriptor'ı, kurulu yazılımın kimliğini gösterir; tek başına tüm bootloader kodunun sağlık kontrolü değildir.

Bootloader güncellemesi SWD ile yapılır. Sonraki **uygulama** yüklemeleri UART üzerinden custom bootloader'a gönderilir. Bootloader 921600 8N1, runtime 115200 8N1; hız geçişini uygulama yönetir. Device Studio bütün seri işlemleri tek worker üzerinden yapar; yükleme sırasında eşzamanlı kontrol komutu göndermez. Kurtarma için USER basılıyken kartı resetleyin. İptal edilen/yarım yükleme baştan tekrar yapılır.

PuTTY/CubeIDE seri terminali gibi başka bir program aynı COM portunu açık tutmamalıdır. Uygulama takılmışsa USER ile reset veya SWD teşhisi kullanılır.

## Firmware paketleri

`Firmware/` altında yerel kaynaklardan üretilen Smartwatch ve Düello paketleri bulunur. Önceki donanım raporu bu yeni binary’lerin fiziksel kartta test edildiği anlamına gelmez. Paket, ZIP içinde `manifest.json` ve `firmware.bin` içerir. Kart, adres, uygulama kimliği, protokol, boyut, vektörler, SHA-256 ve CRC32 yüklemeden önce kontrol edilir. Bootloader Flash içeriğini ayrıca CRC32 ile doğrular. Dijital imza uygulanmaz.

```powershell
python package_firmware.py ../Duello/Firmware/Duello.bin Firmware/Duello.dfw --name Duello
python package_firmware.py ../smart_watch-main/Firmware/Smartwatch.bin Firmware/Smartwatch.dfw --name Smartwatch
python flash_cli.py Firmware/Duello.dfw --port COM5
```

GUI kapatılınca veya USB kesilince Smartwatch, cihaz besleniyorsa çalışmaya devam eder. Düello'nun yürümesi beş saniye komut gelmediğinde durur. Animasyonlar cihazda çizilir; PC yalnız komut ve durum taşır.

## Geri dönüş

Normal uygulama dönüşü: başka `.dfw` paketini yüklemek. Custom bootloader kurulumu öncesine dönüş: `Backup/<timestamp>/before-deviceboot-flash.bin` tam yedeğini ST-LINK/SWD ile `0x08000000` adresine doğrulayarak geri yüklemek. Bu tüm Flash'ı, bootloader'ı ve yedekteki saat kayıtlarını geri getirir. Güncel saat kayıtlarını korumak için restore öncesi son 16 KiB'ı ayrıca yedekleyin. Otomatik eski sürüm rollback'i yoktur.

## Doğrulama

```powershell
python -m unittest discover -s tests -v
# Dikkat: Bu komut gerçek kartın firmware'ini değiştirir; sonrasında Smartwatch'ı geri yükler.
python verify_hardware.py --port COM5
# İlk kurulum da yapılacaksa:
python verify_hardware.py --port COM5 --install
```

`verify_hardware.py` için kart önce bootloader modunda olmalıdır; UI'dan **Bootloader moduna geç** kullanılabilir. `hardware-report.json` gerçek UART yüklemelerinin, runtime komutlarının, kesilmiş yükleme kurtarmasının ve 16 KiB kayıt alanının byte-for-byte korunmasının sonucudur. Otomatik test panel fotoğrafı veya uzun süreli güç kesintisi testi değildir.

ST-LINK işlemleri için STM32CubeProgrammer gerekir. Varsayılan CubeIDE / CubeProgrammer konumları aranır; farklı yerdeyse `STM32_PROGRAMMER_CLI` ortam değişkenine tam exe yolunu verin. Yedekler, yerel Python bağımlılıkları ve kişisel ayarlar Git'e gönderilmez.

## Üçüncü ve sonraki firmware uygulamaları

DeviceBoot **revizyon 2 / protokol 1** yeni uygulama kimliklerini kabul eder. `1=Smartwatch`, `2=Duello` korunur; üçüncü uygulama için `3`, sonrakiler için benzersiz `4..0xFFFFFFFE` kullanın. `0` ve `0xFFFFFFFF` ayrılmıştır. Studio eski bootloader'a üçüncü uygulama yüklemeyi **BEGIN/Flash silme başlamadan** reddeder. Önce yeni `DeviceBoot/Firmware/DeviceBoot.bin` dosyasını **DeviceBoot kur** ile ST-LINK üzerinden güncelleyin; tam yedek alınır.

Yeni firmware aynı linker/vektör düzenini (`0x0800A000`, descriptor `+0x400`, ayrılmış son 16 KiB ve RAM mailbox) kullanmalı; `.app_info` içinde kendi kimliğini/sürümünü vermelidir:

```c
#include "device_contract.h"
__attribute__((section(".app_info"), used))
const device_app_info_t device_app_info = { DEVICE_APP_MAGIC, 3U, 1U, DEVICE_PROTOCOL };
```

Ortak runtime `device_runtime_init("ThirdApp", handler)` ile başlatılır. `handler(const char *command)` geçerli bir JSON nesnesine işaretçi döndürür; `STATUS` dahil uygulama komutlarını işler. HELLO/STATUS/BOOT ve kimlik/sürüm bilgisi ortak runtime tarafından yönetilir. UART/DMA bağlantısı için Düello'nun güncel `main.c` akışını ve ortak derlemedeki kaynak listesini örnek alın. Runtime komutları boşluksuz en fazla 39 ASCII karakterdir; toplam JSON cevap 512 baytlık TX tamponuna sığmalıdır.

Paketlemek için Studio klasöründen:

```sh
python3 package_firmware.py ../ThirdApp/Firmware/ThirdApp.bin Firmware/ThirdApp.dfw --name ThirdApp
# İsteğe bağlı: binary descriptor'ıyla eşleştiğini ayrıca kontrol et:
python3 package_firmware.py ../ThirdApp/Firmware/ThirdApp.bin Firmware/ThirdApp.dfw --name ThirdApp --id 3 --version 1
```

Kimlik ve sürüm varsayılan olarak binary descriptor'ından okunur; uyuşmayan `--id`/`--version` reddedilir. Ad 1–48 karakter olmalı, ASCII harfle başlamalı ve yalnız harf, rakam, `_`, `.`, `-` içermelidir. Smartwatch/Duello/DeviceBoot adları ayrılmıştır. Firmware'in runtime'da bildirdiği ad paket adıyla aynı olmalıdır.

Yeni uygulama yüklendiğinde **Uygulama kontrolü** sekmesi açılır. JSON durum otomatik güncellenir; firmware'in desteklediği komutlar **Gönder** üzerinden iletilir. Özel panel eklemek zorunlu değildir. Düello'nun mevcut paneli korunur. Kartta yine tek uygulama saklanır.

Yerel doğrulama: `python3 -m unittest discover -s tests -v` (Tk içeren Python gerekir). Yeni kaynakların donanım testi için `verify_hardware.py` ayrıca açıkça çalıştırılmalıdır; bu betik gerçek Flash'ı değiştirir.

## ADASLab deney paneli

`ADASLab` üçüncü firmware'dir (ID 3). Panelde ani fren, yavaş araç, önümüze giren araç, sabit takip ve veri kesintisi senaryoları; hedef hız, ACC/AEB açma, ölçüm gürültüsü ve tekrar seçenekleri vardır. Fizik Studio'da, FCW/AEB/ACC denetleyicisi STM32'de çalışır. CSV en son 12000 ölçümü saklar.

```sh
# Fiziksel karta yüklenmiş ADASLab'a bağlanır ve deneyi başlatır:
python3 studio.py --adas
# Fiziksel karta erişmeden derlenen ARM ELF ile çalışır:
python3 -m pip install -r requirements-sim.txt
python3 studio.py --adas-sim
```

ARM simülasyonu için kardeş `ADASLab/build/ADASLab.elf` bulunmalıdır. Yerel SDK `tmp/simulator-libs` mevcutsa kullanılabilir. Bu mod başlıkta açıkça etiketlidir; GPU/ekran donanımını emüle etmez ve sayaçları sıfır gösterir. Fiziksel uygulama yükleme bu modda kapalıdır. `--adas` ise gerçek seri cihazı kullanır; firmware otomatik yüklemez.

Ölçüm aktarımı hedefi 50 ms'dir; fizik zamanı her onaylı cevapta sabit 50 ms ilerler. Geç kalan cevaplar simülasyonu yavaşlatır; komut biriktirilmez, gecikme gizlenmez. Tek worker seri portun sahibidir; simülasyon sürerken yükleme ve diğer komutlar kapalıdır. Tk 80 ms'de yalnız son iki görünümden en güncelini tüketir. Seri cevap gelmezse fizik ilerletilmez. `Duraklat` sonrası PAUSE komutu gönderilir.

`S:...` ölçümü CRC16-CCITT (`0x1021`, başlangıç `0xFFFF`, ondalık son alan), sıra numarası ve simülasyon zamanıyla doğrulanır. Tam protokol ve IRQ/GPU tasarımı `../ADASLab/README.md` içindedir. RTT, 50 ms aşımı, kontrol süresi, GPU tamamlanması, kare sayısı ve en uzun kare ölçülür; raporlanan örnek sonuçlar genel gerçek zaman garantisi değildir.

macOS CubeIDE içindeki CubeProgrammer da artık otomatik bulunur. Fiziksel bootloader kurulum/güncellemesi mevcut tam Flash yedek akışını kullanır.


28 Ekim 2026 yerel kart doğrulamasında dört senaryoda 960 örnek işlendi. Ortalama RTT yaklaşık 32 ms, en büyük 43.47 ms; bu örneklemde 50 ms aşımı yoktu. Ayrıştırma+kontrol en çok 20 µs, en uzun ekran karesi 35 ms ölçüldü. GPU/ekran sayaçları ilerledi ve son 16 KiB ayarlar günlüğü korunmuştu. Sonuçlar `adas-hardware-report.json` içindedir; uzun süreli veya gerçek araç doğrulaması değildir.

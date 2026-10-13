# Device Studio

Windows masaüstü uygulaması: [DeviceBoot](https://github.com/polite10/DeviceBoot) yönetimi, firmware yükleme ve [Düello](https://github.com/polite10/Duello) kontrolü. [Smartwatch](https://github.com/polite10/smart_watch) yüklenince cihaz bağımsız çalışır; Düello yüklenince karakter kontrol paneli açılır.

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
4. **Firmware seç** ile Smartwatch veya Düello `.dfw` paketi seçin; **Yükle ve başlat** ile yükleyin. Cihazdaki mevcut uygulamanın yerini alır; saat kayıt günlüğü korunur.
5. Önce “Firmware doğrulandı”, uygulamanın JSON cevabı geldikten sonra “Uygulama hazır” gösterilir. Düello kontrol sekmesi otomatik açılır.

Bootloader durumu ile çalışan uygulama ayrı gösterilir. Smartwatch veya Düello, bootloader'ın Flash kimliğini bildirir. Bootloader modunda DeviceBoot sürüm/protokol/bellek sınırlarını doğrudan döndürür. Flash descriptor'ı, kurulu yazılımın kimliğini gösterir; tek başına tüm bootloader kodunun sağlık kontrolü değildir.

Bootloader güncellemesi SWD ile yapılır. Sonraki **uygulama** yüklemeleri UART üzerinden custom bootloader'a gönderilir. Bootloader 921600 8N1, runtime 115200 8N1; hız geçişini uygulama yönetir. Device Studio bütün seri işlemleri tek worker üzerinden yapar; yükleme sırasında eşzamanlı kontrol komutu göndermez. Kurtarma için USER basılıyken kartı resetleyin. İptal edilen/yarım yükleme baştan tekrar yapılır.

PuTTY/CubeIDE seri terminali gibi başka bir program aynı COM portunu açık tutmamalıdır. Uygulama takılmışsa USER ile reset veya SWD teşhisi kullanılır.

## Firmware paketleri

`Firmware/` altında iki doğrulanmış örnek paket vardır. Paket, ZIP içinde `manifest.json` ve `firmware.bin` içerir. Kart, adres, uygulama kimliği, protokol, boyut, vektörler, SHA-256 ve CRC32 yüklemeden önce kontrol edilir. Bootloader Flash içeriğini ayrıca CRC32 ile doğrular. Dijital imza uygulanmaz.

```powershell
python package_firmware.py ../Duello/Firmware/Duello.bin Firmware/Duello.dfw --name Duello
python package_firmware.py ../Smartwatch/Firmware/Smartwatch.bin Firmware/Smartwatch.dfw --name Smartwatch
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

# Release Process

Everything needed to turn the source tree into a signed installer, and the
things that must be true before it reaches a customer.

## One-time setup

These four items are prerequisites for the first release. Until they are
done, `python tools/release_check.py` fails and the build refuses to package.

### 1. Generate the licence signing key

```powershell
python tools/licence_admin.py keygen --out vendor-keys.json
```

Paste the printed public key into `VENDOR_PUBLIC_KEY` in
`duddysheet/core/licensing.py`.

**The private key mints licences.** Store it in a password manager or secrets
store and back it up. Never commit it, never ship it, never put it in CI logs.
If you lose it you can no longer issue keys that already-released builds
accept. If it leaks, anyone can generate free licences and your only remedy is
a new key pair, which invalidates every key you have already sold.

Add `vendor-keys.json` to your global gitignore or keep it outside the repo.

### 2. Vendor the GNU licence texts

Qt is used under the LGPL-3.0 and no wheel ships its text, so it must be
added by hand once:

```powershell
curl -o licenses/LGPL-3.0.txt https://www.gnu.org/licenses/lgpl-3.0.txt
curl -o licenses/GPL-3.0.txt  https://www.gnu.org/licenses/gpl-3.0.txt
git add -f licenses/LGPL-3.0.txt licenses/GPL-3.0.txt
```

Distributing Qt without these violates its licence. The build blocks on it.

### 3. Register the domain and support address

`duddysheet/branding.py` points customers at `duddysoftware.com` and
`support@duddysoftware.com`. Both appear in the EULA, the privacy statement,
the About dialog, and the activation dialog. Register the domain and create
the mailbox, or change the values.

### 4. Obtain a code signing certificate

An unsigned installer triggers a full-screen SmartScreen warning that most
buyers will not click past. Buy an OV or EV certificate from a CA such as
DigiCert, Sectigo, or SSL.com. Expect identity validation to take days and to
cost a few hundred dollars a year. An EV certificate carries SmartScreen
reputation immediately; an OV certificate builds it over time and downloads.

Install Inno Setup 6 as well: <https://jrsoftware.org/isdl.php>

## Building a release

```powershell
python -W error -m pytest

$env:CERT_PW = "..."
python tools/build_release.py --sign-cert path\to\cert.pfx --sign-password-env CERT_PW
```

The pipeline runs release checks, collects third-party licences, writes the
Windows version resource from `branding.py`, freezes with PyInstaller, runs
the frozen build's own self-test, signs the executable, builds the installer,
and signs the installer.

Any failing step aborts the build. The self-test is the important one: it
exercises formulas, both file formats, models, charts, PDF export, and
licensing *inside the packaged application*, catching the class of breakage
that only appears after freezing.

For a local build without the prerequisites:

```powershell
python tools/build_release.py --skip-checks --skip-signing --skip-installer
```

Builds made this way are development builds and must not be shared.

## Manual verification before publishing

The automated checks cannot cover these. Do them on a clean Windows machine,
ideally a fresh VM, not your development box.

- [ ] The installer runs without administrator rights and without SmartScreen
      warnings.
- [ ] The application launches and creates a new workbook.
- [ ] Opening a real `.xlsx` model produces correct values.
- [ ] **Print preview matches the printed page on a real printer**, including
      repeated header rows across a page break.
- [ ] PDF export opens correctly in Acrobat and in a browser.
- [ ] A licence key you issued yourself activates, and survives a restart.
- [ ] Uninstalling removes the program and leaves workbooks, settings, and
      the activation intact.
- [ ] The application works with the network adapter disabled.

## Issuing a licence

```powershell
python tools/licence_admin.py issue `
    --private-key-file vendor-keys.json `
    --licensee "Jordan Blake" --email jordan@example.com `
    --edition business --seats 1 --key-id ORDER-1234
```

Send the customer the printed `DS1-...` key. Keys are perpetual unless
`--expires` or `--valid-days` is given.

Record which key went to which order. When a customer loses a key you reissue
it; when a key is published you cannot revoke it, because verification is
offline by design. Revocation would require the phone-home this product
deliberately does not do.

## Versioning

`duddysheet/branding.py` holds the single `VERSION`. It flows into the
installer name, the Windows version resource, the About dialog, and the
release checks. Update it there and nowhere else.

The native file format has its own schema version in
`duddysheet/io/native.py`. Increment it and add a migration whenever the
persisted shape changes; loading refuses files from a newer schema rather
than guessing.

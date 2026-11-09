# سری فوریه و فرمول‌های ریاضی

$$x=2\left(\sin x-\frac{\sin2x}{2}+\frac{\sin3x}{3}-\cdots\right).$$

برای $-\pi<x<\pi$ داریم:

$$x=2\left(\sin x-\frac{\sin2x}{2}+\frac{\sin3x}{3}-\cdots\right).$$

بسط $(\pi-x)(\pi+x)$ در بازهٔ $-\pi\le x\le\pi$ کدام است؟ با تعریف

$$S(x)=\cos x-\frac{\cos2x}{2^2}+\frac{\cos3x}{3^2}-\cdots,$$

گزینه‌ها عبارت‌اند از:

1. $\pi^2-4\left(\sin^2x-\frac{\sin^2 2x}{4}+\frac{\sin^2 3x}{9}-\cdots\right)$
2. $\frac{\pi^2}{3}-4S(x)$
3. $\frac{2\pi^2}{3}+4S(x)$
4. $\frac{\pi^2}{3}+4S(x)$

### پاسخ تشریحی

عبارت خواسته‌شده $\pi^2-x^2$ است. از سری داده‌شده انتگرال می‌گیریم:

$$\frac{x^2}{2}=C-2\sum_{n=1}^{\infty}\frac{(-1)^{n+1}}{n^2}\cos nx.$$

پس $x^2=C_0-4S(x)$. برای تعیین ثابت، میانگین دو طرف را روی یک دوره می‌گیریم. میانگین هر جملهٔ کسینوسی صفر است، بنابراین:

$$C_0=\frac1{2\pi}\int_{-\pi}^{\pi}x^2\,dx=\frac{\pi^2}{3}.$$

در نتیجه:

$$\boxed{\pi^2-x^2=\frac{2\pi^2}{3}+4S(x)}.$$

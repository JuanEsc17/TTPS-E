export default function FondoAdn() {
    return (
        <div
            aria-hidden="true"
            className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-gradient-to-br from-[#EEF4FA] via-[#E6EFF8] to-[#DCE9F5]"
        >
            {/* Resplandores suaves en tonos azul clinico y cian */}
            <div className="absolute -top-32 -right-32 h-[520px] w-[520px] rounded-full bg-[#0891B2]/10 blur-3xl" />
            <div className="absolute -bottom-40 -left-24 h-[520px] w-[520px] rounded-full bg-[#0B4F8A]/10 blur-3xl" />

            {/* Helice principal de ADN en diagonal */}
            <svg
                viewBox="0 0 1200 800"
                preserveAspectRatio="xMidYMid slice"
                className="absolute inset-0 h-full w-full opacity-[0.14]"
                fill="none"
            >
                <defs>
                    <linearGradient id="adn-hebra-1" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="#062846" />
                        <stop offset="50%" stopColor="#0B4F8A" />
                        <stop offset="100%" stopColor="#0891B2" />
                    </linearGradient>
                    <linearGradient id="adn-hebra-2" x1="100%" y1="0%" x2="0%" y2="100%">
                        <stop offset="0%" stopColor="#0891B2" />
                        <stop offset="50%" stopColor="#0B4F8A" />
                        <stop offset="100%" stopColor="#062846" />
                    </linearGradient>
                </defs>

                <g transform="translate(80, -80) rotate(-24 600 400)">
                    {/* Pares de bases (peldaños de la doble helice) */}
                    {[
                        { x: 110, y1: 330, y2: 470 },
                        { x: 165, y1: 300, y2: 500 },
                        { x: 220, y1: 315, y2: 485 },
                        { x: 275, y1: 365, y2: 435 },
                        { x: 385, y1: 365, y2: 435 },
                        { x: 440, y1: 315, y2: 485 },
                        { x: 495, y1: 300, y2: 500 },
                        { x: 550, y1: 330, y2: 470 },
                        { x: 660, y1: 345, y2: 455 },
                        { x: 715, y1: 305, y2: 495 },
                        { x: 770, y1: 310, y2: 490 },
                        { x: 825, y1: 355, y2: 445 },
                        { x: 935, y1: 355, y2: 445 },
                        { x: 990, y1: 310, y2: 490 },
                        { x: 1045, y1: 305, y2: 495 },
                    ].map((rung, idx) => (
                        <g key={idx}>
                            <line
                                x1={rung.x}
                                y1={rung.y1}
                                x2={rung.x}
                                y2={rung.y2}
                                stroke="#0B4F8A"
                                strokeWidth="4"
                                strokeLinecap="round"
                            />
                            <circle cx={rung.x} cy={rung.y1} r="5" fill="#0891B2" />
                            <circle cx={rung.x} cy={rung.y2} r="5" fill="#062846" />
                        </g>
                    ))}

                    {/* Hebra A */}
                    <path
                        d="M 40 400 C 120 240, 240 240, 330 400 C 420 560, 540 560, 620 400 C 700 240, 820 240, 900 400 C 980 560, 1080 560, 1160 400"
                        stroke="url(#adn-hebra-1)"
                        strokeWidth="12"
                        strokeLinecap="round"
                    />
                    {/* Hebra B */}
                    <path
                        d="M 40 400 C 120 560, 240 560, 330 400 C 420 240, 540 240, 620 400 C 700 560, 820 560, 900 400 C 980 240, 1080 240, 1160 400"
                        stroke="url(#adn-hebra-2)"
                        strokeWidth="12"
                        strokeLinecap="round"
                    />
                </g>

                {/* Segunda helice mas tenue en la esquina inferior derecha */}
                <g transform="translate(460, 380) rotate(-24 400 200) scale(0.75)" opacity="0.65">
                    {[120, 180, 240, 360, 420, 480, 600, 660].map((x, idx) => (
                        <line
                            key={idx}
                            x1={x}
                            y1={140}
                            x2={x}
                            y2={260}
                            stroke="#062846"
                            strokeWidth="3.5"
                            strokeLinecap="round"
                        />
                    ))}
                    <path
                        d="M 40 200 C 130 80, 230 80, 300 200 C 370 320, 470 320, 540 200 C 610 80, 710 80, 780 200"
                        stroke="#062846"
                        strokeWidth="10"
                        strokeLinecap="round"
                    />
                    <path
                        d="M 40 200 C 130 320, 230 320, 300 200 C 370 80, 470 80, 540 200 C 610 320, 710 320, 780 200"
                        stroke="#0891B2"
                        strokeWidth="10"
                        strokeLinecap="round"
                    />
                </g>
            </svg>
        </div>
    );
}
